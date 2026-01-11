import json
import re
from typing import Dict, Any, List
from langchain_core.output_parsers import StrOutputParser
from core.llm import get_deepseek_reasoner
from core.prompts import SIMULATOR_CHECK_PROMPT
from core.memory import MemoryManager

class SimulatorAgent:
    def __init__(self, memory_manager: MemoryManager):
        # Simulator 必须使用 R1 (Reasoner) 以保证逻辑严密性
        self.llm = get_deepseek_reasoner()
        self.chain = SIMULATOR_CHECK_PROMPT | self.llm | StrOutputParser()
        self.memory = memory_manager

    def _clean_json(self, text: str) -> str:
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match: return match.group(1)
        match = re.search(r'(\{.*\})', text, re.DOTALL)
        if match: return match.group(1)
        return text.strip()

    def simulate_outline(self, outline: Dict[str, Any], active_characters: List[str]) -> Dict[str, Any]:
        """
        对大纲进行心理沙盘推演。
        """
        print(f"🧠 Simulator: 正在代入角色 {active_characters} 进行行为验证...")

        # 1. 准备角色资料
        # A. 基础档案 (Static Profile + Status)
        basic_info = self.memory.get_character_details(active_characters, query="Simulator Check")
        
        # B. 精神轨迹 (Emotional Inertia)
        mental_curves = self.memory.get_character_mental_curve(active_characters, limit=5)
        
        # 组合 Profile
        profile_text = f"""
=== 基础档案 ===
{basic_info}

=== 📉 精神/情绪轨迹 (Mental Inertia) ===
{mental_curves}
"""
        
        outline_text = json.dumps(outline.get("outline", []), ensure_ascii=False)

        # 2. 调用 LLM
        try:
            response = self.chain.invoke({
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
                print("   ✅ Simulator 通过: 行为逻辑自洽。")
                
            return result

        except Exception as e:
            print(f"   ⚠️ Simulator 思考短路: {e}")
            # 出错时默认通过，避免卡死，但记录警告
            return {"status": "PASS", "warning": str(e)}
