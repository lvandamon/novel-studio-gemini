import json
import re
from typing import Dict, Any, List
from langchain_core.output_parsers import StrOutputParser
from core.llm import get_deepseek_reasoner
from core.prompts import DIRECTOR_EVALUATE_PROMPT, DIRECTOR_SYSTEM_PROMPT
from core.memory import MemoryManager
from core.chaos import ChaosEngine

class DirectorAgent:
    def __init__(self, memory_manager: MemoryManager):
        # Director 使用 R1 (Reasoner) 模型，因为需要极强的逻辑判断能力
        self.llm = get_deepseek_reasoner() 
        self.chain = DIRECTOR_EVALUATE_PROMPT | self.llm | StrOutputParser()
        self.memory = memory_manager
        self.chaos_engine = ChaosEngine(base_probability=0.2) 

    def _clean_json(self, text: str) -> str:
        """
        Robust JSON extractor for Reasoner models that might output thoughts.
        """
        # 1. Remove <think> blocks if present
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        
        # 2. Try to find markdown JSON block
        match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            return match.group(1)
            
        # 3. Try to find the first valid JSON object enclosed in braces
        # This regex looks for { ... } minimally
        match = re.search(r'(\{.*\})', text, re.DOTALL)
        if match:
            return match.group(1)
            
        # 4. Fallback: return original stripped (likely to fail but worth a try)
        return text.strip()

    def evaluate_progress(self, current_chapter: int) -> Dict[str, Any]:
        """
        审计当前进度，并返回指导意见。
        """
        print(f"🎬 Director: 正在审计第 {current_chapter} 章的叙事进度...")
        
        # 1. 获取上下文数据
        plan = self.memory.get_active_plan()
        focus = self.memory.get_narrative_focus()

        # Chaos Check
        chaos_card = self.chaos_engine.roll_for_chaos(current_tension=0.5) # TODO: Use real tension metric
        
        chaos_prompt_injection = ""
        if chaos_card:
            print(f"   🎲 混沌猴子介入! [{chaos_card['category']}] -> {chaos_card['description']}")
            chaos_prompt_injection = f"""
!!! 突发状况 (CHAOS EVENT) !!!
系统强制触发了一个意外事件：【{chaos_card['category']} - {chaos_card['description']}】
指令：你必须将此事件整合进当前的叙事决策中。它必须在接下来的 1-2 章内发生，打破原有的线性规划。
"""
        
        # --- 构建分级历史视图 (Fractal History) ---
        
        # A. 历史卷综述 (Long-term)
        vol_sums = self.memory.get_aggregated_summaries("volume")
        vol_text = "\n".join([f"【卷{v['start']}-{v['end']}】{v['content']}" for v in vol_sums]) or "（暂无完结卷）"
        
        # B. 近期阶段综述 (Medium-term, last 3 batches)
        batch_sums = self.memory.get_aggregated_summaries("batch_10")
        recent_batches = batch_sums[-3:] if batch_sums else []
        batch_text = "\n".join([f"【阶段{b['start']}-{b['end']}】{b['content']}" for b in recent_batches]) or "（暂无阶段综述）"
        
        # C. 当前未归档章节 (Short-term)
        # 如果有 batch，从最后一个 batch 结束处开始；否则从头或者是最近 10 章
        last_batch_end = recent_batches[-1]['end'] if recent_batches else 0
        start_recent = max(last_batch_end + 1, current_chapter - 9) 
        # 保证至少看最近 3 章 (即使刚归档)
        start_recent = min(start_recent, max(1, current_chapter - 2))

        summaries = []
        for i in range(start_recent, current_chapter + 1):
            s = self.memory.get_chapter_summary(i)
            summaries.append(f"Ch{i}: {s}")
        recent_text = "\n".join(summaries)
        
        full_history_context = f"""
=== 📜 历史卷宗 (Volume History) ===
{vol_text}

=== 📅 近期形势 (Recent Batches) ===
{batch_text}

=== ⚡️ 当前画面 (Immediate Context) ===
{recent_text}
"""

        # 计算进度
        arc_data = plan.get("arc", {}) or {}
        start_chapter = arc_data.get("start_chapter", 1)
        chapters_used = current_chapter - start_chapter + 1
        
        # 2. 调用 LLM
        try:
            response = self.chain.invoke({
                "volume_name": plan.get("volume", {}).get("name", "未命名卷"),
                "volume_goal": plan.get("volume", {}).get("goal", "无"),
                "arc_name": arc_data.get("name", "未命名单元"),
                "arc_goal": arc_data.get("goal", "无"),
                "start_chapter": start_chapter,
                "current_chapter": current_chapter,
                "chapters_used": chapters_used,
                "end_chapter_estimated": arc_data.get("end_chapter_estimated", "未设定"),
                "recent_summaries": full_history_context, # 传入分级历史
                "current_focus": json.dumps(focus, ensure_ascii=False) + chaos_prompt_injection # 注入混沌
            })
            
            # 3. 解析结果 (Robust)
            cleaned_json = self._clean_json(response)
            decision = json.loads(cleaned_json)
            
            # 4. 执行决策 (自动更新 Narrative Focus)
            self._apply_decision(decision)
            
            return decision

        except json.JSONDecodeError as e:
            print(f"   ⚠️ Director JSON 解析失败: {e}")
            # print(f"   RAW OUTPUT: {response[:200]}...") 
            return {"error": "JSON Parse Error"}
        except Exception as e:
            print(f"   ⚠️ Director 思考短路: {e}")
            return {"error": str(e)}

    def _apply_decision(self, decision: Dict[str, Any]):
        """将导演的决策应用到数据库"""
        
        # 更新叙事焦点
        focus_update = decision.get("narrative_focus_update")
        if focus_update:
            # 这里的逻辑是：Director 的决定具有最高优先级，覆盖当前的 Focus
            current_focus = self.memory.get_narrative_focus()
            
            self.memory.update_narrative_focus(
                volume=current_focus.get("volume"), # 卷名通常不轻易变
                arc=current_focus.get("arc"),       # 单元名也不变
                beat=focus_update.get("current_beat", current_focus.get("beat")),
                goal=focus_update.get("current_goal", current_focus.get("goal")),
                conflict=focus_update.get("current_conflict", current_focus.get("conflict")),
                state=focus_update.get("world_state_summary", current_focus.get("state"))
            )
            print(f"   🎬 叙事指令已下达: {decision.get('pacing_directive')} - {focus_update.get('current_beat')}")

        # 如果有全局事件，记录到 memory (作为 System Event)
        global_event = decision.get("global_event")
        if global_event:
            self.memory.log_event(
                chapter_num=0, # 0 表示系统级/世界级事件
                character_name="WORLD",
                event_type="GLOBAL_EVENT",
                description=global_event,
                layer="Reality"
            )
            print(f"   🌍 世界线变动: {global_event}")
            
        # Log critique
        if decision.get("critique"):
            print(f"   📢 导演锐评: {decision.get('critique')}")