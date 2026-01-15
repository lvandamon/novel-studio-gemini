import json
import re
from typing import Dict, Any, List
from langchain_core.output_parsers import StrOutputParser
from core.llm import get_deepseek_reasoner
from core.prompts import DIRECTOR_EVALUATE_PROMPT
from core.memory import MemoryManager
from core.chaos import ChaosEngine
from core.json_repair import clean_json
from agents.drift_detector import DriftDetector

class DirectorAgent:
    def __init__(self, memory_manager: MemoryManager):
        # Director 使用 R1 (Reasoner)
        self.llm = get_deepseek_reasoner() 
        self.chain = DIRECTOR_EVALUATE_PROMPT | self.llm | StrOutputParser()
        self.memory = memory_manager
        self.chaos_engine = ChaosEngine(memory_manager=self.memory, base_probability=0.2) 
        self.drift_detector = DriftDetector(memory_manager)

    def _fetch_structural_context(self, current_chapter: int) -> str:
        """结构化审计上下文 (Mid-Range View)"""
        # 1. Active Hooks (Including Stale)
        hooks = self.memory.get_active_foreshadowing()
        stale_hooks = self.memory.get_stale_unresolved_hooks(limit=3)
        
        lines = []
        
        # Stale First
        if stale_hooks:
            lines.append("💀 [STALE/URGENT] 以下伏笔已滞后太久，需尽快推进：")
            for h in stale_hooks:
                lines.append(f"   - [ID:{h['id']}] (Since Ch{h['chapter_created']}) {h['content']}")
        
        # Regular High Importance
        sorted_hooks = sorted(hooks, key=lambda x: -x['importance'])
        for h in sorted_hooks:
            if any(sh['id'] == h['id'] for sh in stale_hooks): continue # Skip if already shown as stale
            
            imp_mark = "🔥" if h['importance'] >= 8 else "🔸"
            lines.append(f"- {imp_mark} [ID:{h['id']}] (Ch{h['chapter']}) {h['content']}")
            
        hooks_text = "\n".join(lines) if lines else "无活跃伏笔"
            
        # 2. Open Conflicts
        conflict_text = self.memory.graph.get_unresolved_conflicts(limit=10)
        
        return f"""
=== 🎣 待回收伏笔 (Open Hooks) ===
{hooks_text}

=== ⚔️ 未闭环冲突 (Open Conflicts) ===
{conflict_text}
"""

    def _format_telemetry(self, current_chapter: int) -> str:
        """格式化遥测数据"""
        history = self.memory.get_metrics_history(limit=5)
        if not history: return "（暂无遥测数据）" 
            
        recent = history[-5:]
        lines = []
        avg_tension = 0
        for h in recent:
            tension_bar = "🔥" * (h['tension'] // 20)
            line = f"- Ch{h['chapter']}: Tension {h['tension']} {tension_bar} | Pacing {h['pacing']}"
            lines.append(line)
            avg_tension += h['tension']
            
        avg_tension /= len(recent)
        trend = "平稳"
        if avg_tension > 75: trend = "高压"
        elif avg_tension < 30: trend = "松弛"
        
        return f"趋势: {trend} (Avg: {avg_tension:.1f})\n" + "\n".join(lines)

    def evaluate_progress(self, current_chapter: int, high_risk_flag: bool = False) -> Dict[str, Any]:
        """审计进度并返回决策"""
        print(f"🎬 Director: 审计第 {current_chapter} 章...")
        
        risk_context = ""
        if high_risk_flag:
            risk_context = "\n!!! RED ALERT: 高风险预警，优先修复逻辑 !!!\n"

        drift_report = ""
        if self.drift_detector.should_trigger_detection(current_chapter):
             drift_report = self.drift_detector.generate_full_report(current_chapter)

        # Context Gathering
        plan = self.memory.get_active_plan()
        focus = self.memory.get_narrative_focus()
        telemetry = self._format_telemetry(current_chapter)
        structural = self._fetch_structural_context(current_chapter)
        
        # History
        summaries = []
        for i in range(max(1, current_chapter - 5), current_chapter):
             summaries.append(f"Ch{i}: {self.memory.get_chapter_summary(i)}")
        recent_text = "\n".join(summaries)

        # Chaos
        chaos_card = self.chaos_engine.roll_for_chaos(current_chapter, current_tension=50) # simplify
        chaos_txt = ""
        if chaos_card:
            chaos_txt = f"\n!!! CHAOS EVENT: {chaos_card['description']} !!!\n"

        # LLM Call
        try:
            arc_data = plan.get("arc", {})
            response = self.chain.invoke({
                "volume_name": plan.get("volume", {}).get("name", "Unknown"),
                "volume_goal": plan.get("volume", {}).get("goal", ""),
                "arc_name": arc_data.get("name", "Unknown"),
                "arc_goal": arc_data.get("goal", ""),
                "start_chapter": arc_data.get("start_chapter", 1),
                "current_chapter": current_chapter,
                "chapters_used": current_chapter - arc_data.get("start_chapter", 1),
                "end_chapter_estimated": arc_data.get("end_chapter_estimated", "?"),
                "recent_summaries": recent_text,
                "telemetry_data": telemetry + risk_context + chaos_txt + f"\n{drift_report}",
                "current_focus": json.dumps(focus, ensure_ascii=False),
                "structural_analysis": structural,
                "chaos_injection": chaos_txt
            })
            
            decision = json.loads(clean_json(response))
            self._apply_decision(decision)
            return decision

        except Exception as e:
            print(f"   ⚠️ Director Error: {e}")
            return {"error": str(e)}

    def _apply_decision(self, decision: Dict[str, Any]):
        focus_update = decision.get("narrative_focus_update")
        if focus_update:
            self.memory.update_narrative_focus(
                volume=None, arc=None, # Keep existing
                beat=focus_update.get("current_beat"),
                goal=focus_update.get("current_goal"),
                conflict=focus_update.get("current_conflict"),
                state=focus_update.get("world_state_summary"),
                pacing_directive=decision.get("pacing_directive")
            )
            print(f"   🎬 叙事指令: {decision.get('pacing_directive')} | Beat: {focus_update.get('current_beat')}")
        
        if decision.get("global_event"):
             self.memory.log_event(0, "WORLD", "GLOBAL_EVENT", decision.get("global_event"))