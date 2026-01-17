import random
import json
from typing import Optional, Dict
from core.memory import MemoryManager
from core.llm import get_deepseek_chat
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from core.json_repair import clean_json

class ChaosEngine:
    """
    熵增引擎 v3.0 (Generative Chaos)
    
    不再是查表，而是根据当前语境生成独特的意外。
    """
    
    def __init__(self, memory_manager: MemoryManager, base_probability: float = 0.15):
        self.memory = memory_manager
        self.base_probability = base_probability
        self.llm = get_deepseek_chat(temperature=0.7) # High temp for creativity
        
        # 定义各类别的冷却时间 (章数)
        self.cooldown_rules = {
            "Environment": 15,
            "Character": 10,
            "Information": 5,
            "Enemy": 8,
            "Item": 8
        }
        
        # Generation Prompt
        self.gen_prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个【戏剧性意外生成器 (Chaos Generator)】。
你的任务是根据当前剧情上下文，设计一个突发的、合理的、能打破平衡的意外事件。

原则：
1. **情境相关**：如果地点在火山，不要生成水灾；如果地点在密室，不要生成天降陨石。
2. **意料之外，情理之中**：意外必须符合世界观逻辑。
3. **破坏平衡**：意外必须迫使主角改变当前的行动计划。

类别定义：
- **Environment**: 天气、地形、灵气环境突变。
- **Character**: 盟友背叛、路人乱入、旧伤复发、走火入魔。
- **Information**: 发现情报是假的、得知惊天秘密。
- **Enemy**: 第三方势力介入、宿敌提前登场。
- **Item**: 关键道具损坏、遗失、或突然觉醒。

输出 JSON (严禁 Markdown):
{{
    "category": "Environment" | "Character" | "Information" | "Enemy" | "Item",
    "description": "一句话描述这个意外",
    "impact": "对主角造成的直接困扰",
    "cooldown_cost": 10 // 冷却章数建议
}}
"""),
            ("user", """
【当前地点】：{location}
【在场角色】：{characters}
【当前气氛】：{atmosphere}
【核心冲突】：{conflict}

请生成一个高戏剧性的意外。不要生成以下冷却中的类别：{frozen_categories}
""")
        ])
        
        self.chain = self.gen_prompt | self.llm | StrOutputParser()

    def roll_for_chaos(self, current_chapter: int, current_tension: float) -> Optional[Dict[str, str]]:
        """
        根据当前章数和紧张度，决定是否触发意外。
        """
        
        # 1. 检查冷却池
        frozen_categories = self.memory.get_active_cooldowns(current_chapter)
        # Note: In generative mode, we pass frozen cats to LLM as constraint, 
        # instead of filtering a static list.
        
        # 2. 动态概率调整
        probability = self.base_probability
        
        if current_tension > 0.8:
            probability *= 0.2 # 高潮期保护
        elif current_tension < 0.3:
            probability *= 2.5 # 平淡期催化
        
        # 3. 掷骰子
        if random.random() < probability:
            return self._generate_event(current_chapter, frozen_categories)
            
        return None

    def _generate_event(self, current_chapter: int, frozen_categories: list) -> Dict[str, str]:
        # Gather Context
        plan = self.memory.get_active_plan()
        focus = self.memory.get_narrative_focus()
        
        # Get active chars from last updated (approximate)
        # Ideally passed from Director, but here we query DB
        # For simplicity, we assume generic context or query recent
        
        try:
            # Simple context gathering
            location = "未知区域"
            characters = "主角团队"
            
            response = self.chain.invoke({
                "location": location,
                "characters": characters,
                "atmosphere": f"Tension: Unknown",
                "conflict": focus.get('conflict', 'Unknown'),
                "frozen_categories": ", ".join(frozen_categories)
            })
            
            data = json.loads(clean_json(response))
            category = data.get("category", "Environment")
            
            # Apply cooldown
            duration = self.cooldown_rules.get(category, 10)
            self.memory.set_chaos_cooldown(category, current_chapter, duration)
            
            print(f"   🎲 Chaos Generated: [{category}] {data['description']}")
            
            return {
                "type": "Chaos Event",
                "category": category,
                "description": data['description'],
                "instruction": f"Chaos triggered! Impact: {data.get('impact')}. You MUST integrate this event immediately."
            }
            
        except Exception as e:
            print(f"   ⚠️ Chaos Generation Failed: {e}")
            return None