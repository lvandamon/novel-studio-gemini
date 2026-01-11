import json
import re
from typing import Dict, Any, List
from langchain_core.output_parsers import StrOutputParser
from core.llm import get_deepseek_reasoner
from core.prompts import DIRECTOR_EVALUATE_PROMPT, DIRECTOR_SYSTEM_PROMPT
from core.memory import MemoryManager

class DirectorAgent:
    def __init__(self, memory_manager: MemoryManager):
        # Director 使用 R1 (Reasoner) 模型，因为需要极强的逻辑判断能力
        self.llm = get_deepseek_reasoner() 
        self.chain = DIRECTOR_EVALUATE_PROMPT | self.llm | StrOutputParser()
        self.memory = memory_manager

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
        
        # 获取最近 5 章摘要
        summaries = []
        for i in range(max(1, current_chapter - 4), current_chapter + 1):
            s = self.memory.get_chapter_summary(i)
            summaries.append(f"Ch{i}: {s}")
        recent_summaries_text = "\n".join(summaries)

        # 计算进度
        arc_data = plan.get("arc", {{}}) or {{}}
        start_chapter = arc_data.get("start_chapter", 1)
        chapters_used = current_chapter - start_chapter + 1
        
        # 2. 调用 LLM
        try:
            response = self.chain.invoke({
                "volume_name": plan.get("volume", {{}}).get("name", "未命名卷"),
                "volume_goal": plan.get("volume", {{}}).get("goal", "无"),
                "arc_name": arc_data.get("name", "未命名单元"),
                "arc_goal": arc_data.get("goal", "无"),
                "start_chapter": start_chapter,
                "current_chapter": current_chapter,
                "chapters_used": chapters_used,
                "end_chapter_estimated": arc_data.get("end_chapter_estimated", "未设定"),
                "recent_summaries": recent_summaries_text,
                "current_focus": json.dumps(focus, ensure_ascii=False)
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