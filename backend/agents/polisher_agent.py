from typing import Dict, Any, List
from langchain_core.output_parsers import StrOutputParser
from core.llm import get_deepseek_chat
from core.prompts import POLISHER_EXECUTE_PROMPT
from core.memory import MemoryManager

class PolisherAgent:
    def __init__(self, memory_manager: MemoryManager):
        self.llm = get_deepseek_chat(temperature=0.7) # Higher temp for creativity
        self.chain = POLISHER_EXECUTE_PROMPT | self.llm | StrOutputParser()
        self.memory = memory_manager

    def polish_draft(self, draft: str, outline_data: Dict[str, Any]) -> str:
        """
        对草稿进行润色。
        """
        scene_location = outline_data.get("scene_location", "未知")
        atmosphere_dict = outline_data.get("atmosphere", {})
        
        # 1. 确定场景类型 (Simple heuristic)
        # 理想情况下 ContextManager 会给出 intent，但这里我们可以简单推断，或者从 outline_data 里看有没有 intent 字段
        # 假设 outline_data 可能包含 'narrative_focus'
        
        # 简单的关键词匹配来决定 Style Category
        categories = ["General"]
        draft_lower = draft.lower()
        if "杀" in draft or "血" in draft or "死" in draft or "fight" in draft_lower:
            categories.append("Action")
        if "“" in draft or "\"" in draft: # 有对话
            categories.append("Dialogue")
        if "想" in draft or "思索" in draft:
            categories.append("InnerMonologue")
            
        # 2. 从数据库获取 Style Guide
        # 优先获取 Action (Combat), 其次 Dialogue
        style_samples = self.memory.get_style_examples(tags=categories, limit=3)
        
        if not style_samples:
            style_samples = "（无特定样板，请保持网文快节奏风格）"

        # 3. 构造氛围描述
        atm_str = f"基调: {atmosphere_dict.get('tone', '正常')} | 紧张度: {atmosphere_dict.get('tension', 0.5)}"
        if atmosphere_dict.get('color_palette'):
            atm_str += f" | 色调: {atmosphere_dict.get('color_palette')}"
        if atmosphere_dict.get('sensory_focus'):
            atm_str += f" | 感官侧重: {atmosphere_dict.get('sensory_focus')}"

        print(f"✨ Polisher: 正在润色 (Style: {categories}, Atm: {atm_str})...")
        
        try:
            polished = self.chain.invoke({
                "draft": draft,
                "style_guide": style_samples,
                "scene_type": "/".join(categories),
                "atmosphere": atm_str
            })
            return polished
        except Exception as e:
            print(f"   ⚠️ Polishing Failed: {e}")
            return draft # Fallback to original
