import json
import re
from typing import Dict, Any, List
from langchain_core.output_parsers import StrOutputParser
from core.llm import get_deepseek_reasoner
from core.prompts import DIRECTOR_EVALUATE_PROMPT, DIRECTOR_SYSTEM_PROMPT
from core.memory import MemoryManager
from core.chaos import ChaosEngine
from core.json_repair import repair_and_parse, clean_json, JSONRepairError
from agents.drift_detector import DriftDetector # 🔥 P4新增

class DirectorAgent:
    def __init__(self, memory_manager: MemoryManager):
        # Director 使用 R1 (Reasoner) 模型，因为需要极强的逻辑判断能力
        self.llm = get_deepseek_reasoner() 
        self.chain = DIRECTOR_EVALUATE_PROMPT | self.llm | StrOutputParser()
        self.memory = memory_manager
        self.chaos_engine = ChaosEngine(memory_manager=self.memory, base_probability=0.2) 
        self.drift_detector = DriftDetector(memory_manager) # 🔥 P4新增: 性格漂移监测

    def _clean_json(self, text: str) -> str:
        """
        🔥 P4升级: 使用专业的JSON修复模块

        替代原来脆弱的正则处理
        """
        return clean_json(text)

    def _fetch_structural_context(self, current_chapter: int) -> str:
        """
        🔥 P0新增: 结构化审计上下文 (The Director's Eye)
        
        从图谱和数据库中提取深层结构信息，防止导演"瞎指挥"。
        1. 待处理伏笔 (Open Hooks)
        2. 未闭环冲突 (Open Conflicts) - 🔥 P5升级: 直接从图谱获取
        """
        # 1. 获取伏笔
        hooks = self.memory.get_active_foreshadowing()
        hooks_text = "无活跃伏笔"
        if hooks:
            # 按重要性排序
            sorted_hooks = sorted(hooks, key=lambda x: -x['importance'])
            lines = []
            for h in sorted_hooks:
                imp_mark = "🔥" if h['importance'] >= 8 else "🔸"
                lines.append(f"- {imp_mark} [ID:{h['id']}] (Ch{h['chapter']}) {h['content']}")
            hooks_text = "\n".join(lines)
            
        # 2. 获取未闭环冲突 (Open Conflicts)
        conflict_text = self.memory.graph.get_unresolved_conflicts(limit=10)
        
        return f"""
=== 🎣 待回收伏笔 (Open Hooks) ===
{hooks_text}

=== ⚔️ 未闭环冲突 (Open Conflicts - Must Resolve) ===
{conflict_text}
"""

    def _format_telemetry(self, current_chapter: int) -> str:
        """格式化最近的遥测数据"""
        # 获取最近 5 章数据
        history = self.memory.get_metrics_history(limit=5) # 这里的 limit 应该在 memory 方法里实现，或者取回后切片
        # 由于 memory.get_metrics_history 实现是全部返回，我们在这里切片
        if not history:
            return "（暂无遥测数据，系统处于初始化阶段）"
            
        recent = history[-5:]
        
        lines = []
        avg_tension = 0
        for h in recent:
            # 简单的图形化表示
            tension_bar = "🔥" * (h['tension'] // 20)
            pacing_bar = "⏩" * (h['pacing'] // 20)
            lines.append(f"- Ch{h['chapter']}: Tension {h['tension']} {tension_bar} | Pacing {h['pacing']} {pacing_bar} | Logic {h['plot_logic']}")
            avg_tension += h['tension']
            
        avg_tension /= len(recent)
        trend = "平稳"
        if avg_tension > 75: trend = "高压 (High Tension)"
        elif avg_tension < 30: trend = "松弛 (Low Tension)"
        
        return f"趋势分析: {trend} (Avg Tension: {avg_tension:.1f})\n" + "\n".join(lines)

    def evaluate_progress(self, current_chapter: int, high_risk_flag: bool = False) -> Dict[str, Any]:
        """
        审计当前进度，并返回指导意见。
        """
        print(f"🎬 Director: 正在审计第 {current_chapter} 章的叙事进度...")
        
        # 🔥 P4新增: 紧急避险模式 (Damage Control)
        risk_context = ""
        if high_risk_flag:
            print("   🚨 Director: 接到高风险预警! 启动损管模式 (Damage Control Mode)。")
            risk_context = """
!!! 红色警报 (RED ALERT) !!!
系统检测到前序章节存在严重逻辑隐患或被模拟器多次驳回。
【指令】: 本次规划必须优先进行“逻辑修复”和“伏笔填坑”。
1. 暂停推进新的高风险主线。
2. 通过对话或侧面描写修补之前的逻辑漏洞。
3. 确保人物动机回归理性。
"""

        # 🔥 P4新增: 性格漂移检测
        drift_report = ""
        if self.drift_detector.should_trigger_detection(current_chapter):
            print(f"   🧬 Director: 触发周期性性格漂移检测...")
            drift_report = self.drift_detector.generate_full_report(current_chapter)
            if "严重漂移" in drift_report:
                print("   ⚠️ 检测到严重性格漂移，已注入 Director 上下文。")
            else:
                print("   ✅ 性格检测通过。")

        # 1. 获取上下文数据
        plan = self.memory.get_active_plan()
        focus = self.memory.get_narrative_focus()

        # Chaos Check & Telemetry
        metrics_history = self.memory.get_metrics_history() # fetch all
        
        real_tension = 50.0
        if metrics_history:
            last_chapter_data = metrics_history[-1]
            real_tension = last_chapter_data.get("tension", 50) / 100.0
            print(f"   📊 Director: 检测到上一章真实张力为 {real_tension:.2f}")
            
        # 格式化遥测数据用于 Prompt
        telemetry_text = self._format_telemetry(current_chapter)
            
        chaos_card = self.chaos_engine.roll_for_chaos(current_chapter, current_tension=real_tension)
        
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

        # --- 🔥 结构化审计 (Structure Audit) ---
        structural_context = self._fetch_structural_context(current_chapter)

        # 计算进度
        arc_data = plan.get("arc", {})
        start_chapter = arc_data.get("start_chapter", 1)
        chapters_used = current_chapter - start_chapter + 1
        
        # 2. 调用 LLM
        try:
            # 组合额外的 Context
            combined_telemetry = telemetry_text
            if risk_context:
                combined_telemetry += f"\n\n{risk_context}"
            if drift_report:
                combined_telemetry += f"\n\n=== 🧬 性格漂移报告 ===\n{drift_report}"

            response = self.chain.invoke({
                "volume_name": plan.get("volume", {}).get("name", "未命名卷"),
                "volume_goal": plan.get("volume", {}).get("goal", "无"),
                "arc_name": arc_data.get("name", "未命名单元"),
                "arc_goal": arc_data.get("goal", "无"),
                "start_chapter": start_chapter,
                "current_chapter": current_chapter,
                "chapters_used": chapters_used,
                "end_chapter_estimated": arc_data.get("end_chapter_estimated", "未设定"),
                "recent_summaries": full_history_context,
                "telemetry_data": combined_telemetry, # Injected here
                "current_focus": json.dumps(focus, ensure_ascii=False),
                "structural_analysis": structural_context,
                "chaos_injection": chaos_prompt_injection 
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
            
            # 计算 Echo Count Delta
            # 简单的启发式：如果 Director 认为这次点题了 (在 feedback 里表扬)，我们可以手动加分
            # 或者干脆让 Director 在 JSON 里直接返回 delta？
            # 现在的 Prompt 里没写返回 delta，暂时由人类或者分析 feedback 来决定太复杂
            # 我们假设只要 global_event 涉及主题，或者 feedback 是正向的，就加 1
            # 这里简化处理：暂不自动更新 echo count，留给后续 Reviewer 来打分更合适。
            
            self.memory.update_narrative_focus(
                volume=current_focus.get("volume"), 
                arc=current_focus.get("arc"),       
                beat=focus_update.get("current_beat", current_focus.get("beat")),
                goal=focus_update.get("current_goal", current_focus.get("goal")),
                conflict=focus_update.get("current_conflict", current_focus.get("conflict")),
                state=focus_update.get("world_state_summary", current_focus.get("state")),
                current_theme=focus_update.get("current_theme", current_focus.get("theme")),
                pacing_directive=decision.get("pacing_directive", "Normal")
            )
            print(f"   🎬 叙事指令已下达: {decision.get('pacing_directive')} - {focus_update.get('current_beat')}")

        # 如果有全局事件，记录到 memory (作为 System Event)
        global_event = decision.get("global_event")
        if global_event:
            self.memory.log_event(
                chapter_num=0, 
                character_name="WORLD",
                event_type="GLOBAL_EVENT",
                description=global_event,
                layer="Reality"
            )
            print(f"   🌍 世界线变动: {global_event}")
            
        # Log critique and thematic feedback
        if decision.get("thematic_feedback"):
             print(f"   🎼 母题回响: {decision.get('thematic_feedback')}")
        if decision.get("critique"):
            print(f"   📢 导演锐评: {decision.get('critique')}")
