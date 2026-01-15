import json
import re
from typing import Dict, Any, List
from langchain_core.output_parsers import StrOutputParser
from core.llm import get_deepseek_reasoner
from core.prompts import SIMULATOR_CHECK_PROMPT
from core.memory import MemoryManager
from core.physics import PhysicalityEngine
from core.causality import CausalitySimulator # 🔥 New Import

class SimulatorAgent:
    def __init__(self, memory_manager: MemoryManager):
        # Simulator 必须使用 R1 (Reasoner) 以保证逻辑严密性
        self.llm = get_deepseek_reasoner()
        self.chain = SIMULATOR_CHECK_PROMPT | self.llm | StrOutputParser()
        self.memory = memory_manager
        self.physics = PhysicalityEngine(memory_manager)
        self.causality_engine = CausalitySimulator(memory_manager) # 🔥 P10新增

    def _clean_json(self, text: str) -> str:
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match: return match.group(1)
        match = re.search(r'(\{.*\})', text, re.DOTALL)
        if match: return match.group(1)
        return text.strip()

    def simulate_outline(self, outline: Dict[str, Any], active_characters: List[str]) -> Dict[str, Any]:
        """
        对大纲进行全维度（物理/因果/心理）沙盘推演。
        """
        print(f"🧠 Simulator: 正在对 {active_characters} 进行全维度逻辑验证...")

        # 1. 准备资料
        
        # A. 物理快照 (Physical Snapshot)
        # 获取当前场景地点（从大纲里拿）
        scene_loc = outline.get("scene_location", "未知")
        physical_snapshot = self.physics.get_hard_constraints_for_prompt(active_characters, scene_loc)
        
        # B. 因果图谱 (Causal Graph)
        # 提取这些角色之间的关系网
        causal_graph = self.memory.graph.get_multi_entity_relationships(active_characters)
        
        # C. 心理档案 (Mental Profile)
        basic_info = self.memory.get_character_details(active_characters, query="Simulator Check")
        mental_curves = self.memory.get_character_mental_curve(active_characters, limit=5)

        # 🔥 P1修复: 强制注入黄金锚点 (Golden Anchors)
        anchors_text = ""
        for char in active_characters:
            anchor = self.memory.get_character_anchors(char)
            if anchor:
                anchors_text += f"{anchor}\n"

        profile_text = f"""
=== ⚓️ 黄金锚点 (Immutable Anchors) - 最高优先级 ===
{anchors_text if anchors_text else "（无特殊锚点）"}

=== 基础档案 ===
{basic_info}

=== 📉 精神/情绪轨迹 ===
{mental_curves}
"""
        
        outline_text = json.dumps(outline.get("outline", []), ensure_ascii=False)

        # 2. 调用 LLM 进行常规逻辑检查
        try:
            response = self.chain.invoke({
                "physical_snapshot": physical_snapshot,
                "causal_graph": causal_graph,
                "character_profiles": profile_text,
                "outline": outline_text
            })

            cleaned = self._clean_json(response)
            result = json.loads(cleaned)
            
            # 3. 常规检查结果处理
            if result.get("status") == "REJECT":
                print(f"   ❌ Simulator 驳回: {result.get('conflict_analysis')}")
                print(f"   🔧 修改建议: {result.get('suggestion')}")
                return result # 直接返回驳回结果

            # 🔥 P10新增: 因果推演 (Causality Check)
            # 只有常规检查通过后，才跑昂贵的因果推演
            print("   🔮 启动因果推演 (Butterfly Effect Check)...")
            
            # 从大纲中提取关键动作 (简单启发式：取第一句和最后一句)
            outline_list = outline.get("outline", [])
            if outline_list:
                key_action = f"{outline_list[0]} ... {outline_list[-1]}"
                
                causality_res = self.causality_engine.simulate_action(
                    action_description=key_action, 
                    target_entities=active_characters
                )
                
                if causality_res.get("risk_level") in ["HIGH", "CRITICAL"]:
                    # 如果因果风险过高，强制驳回或注入警告
                    print(f"   🛑 因果模拟发现致命风险: {causality_res.get('verdict')}")
                    # 我们可以选择 REJECT，或者只是附加警告
                    # 这里选择 REJECT，因为我们要扼杀长线逻辑漏洞
                    return {
                        "status": "REJECT",
                        "conflict_analysis": f"【未来因果冲突】此剧情将导致严重后果：{causality_res.get('plan_disruption')}",
                        "suggestion": f"请参考后果调整大纲：{json.dumps(causality_res.get('consequences'), ensure_ascii=False)}"
                    }

            print("   ✅ Simulator 全维度通过。")
            return result

        except Exception as e:
            print(f"   ⚠️ Simulator 思考短路: {e}")
            # 出错时默认通过，避免卡死，但记录警告
            return {"status": "PASS", "warning": str(e)}
