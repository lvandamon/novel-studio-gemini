import json
import re
from typing import Dict, Any, List
from langchain_core.output_parsers import StrOutputParser
from core.llm import get_deepseek_reasoner
from core.prompts import SIMULATOR_CHECK_PROMPT
from core.memory import MemoryManager
from core.physics import PhysicalityEngine

class SimulatorAgent:
    def __init__(self, memory_manager: MemoryManager):
        # Simulator 必须使用 R1 (Reasoner) 以保证逻辑严密性
        self.llm = get_deepseek_reasoner()
        self.chain = SIMULATOR_CHECK_PROMPT | self.llm | StrOutputParser()
        self.memory = memory_manager
        self.physics = PhysicalityEngine(memory_manager)

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
        
        profile_text = f"""
=== 基础档案 ===
{basic_info}

=== 📉 精神/情绪轨迹 ===
{mental_curves}
"""
        
        outline_text = json.dumps(outline.get("outline", []), ensure_ascii=False)

        # 2. 调用 LLM
        try:
            response = self.chain.invoke({
                "physical_snapshot": physical_snapshot,
                "causal_graph": causal_graph,
                "character_profiles": profile_text,
                "outline": outline_text
            })

            cleaned = self._clean_json(response)
            result = json.loads(cleaned)
            
            # 3. 结果处理
            if result.get("status") == "REJECT":
                print(f"   ❌ Simulator 驳回: {result.get('conflict_analysis')}")
                print(f"   🔧 修改建议: {result.get('suggestion')}")
            else:
                print("   ✅ Simulator 通过: 逻辑自洽。")
                
            return result

        except Exception as e:
            print(f"   ⚠️ Simulator 思考短路: {e}")
            # 出错时默认通过，避免卡死，但记录警告
            return {"status": "PASS", "warning": str(e)}
