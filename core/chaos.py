import random
from typing import Optional, Dict

class ChaosEngine:
    """
    熵增引擎 (Chaos Engine) - 为故事引入随机性与意外性。
    
    机制：
    1. 每一章都有一定概率触发 "Chaos Event" (混沌事件)。
    2. 事件类型从预定义的 "Tropes Deck" (套路库) 中随机抽取。
    3. 旨在打破线性叙事，强迫 Director 和 Editor 处理突发状况。
    """
    
    def __init__(self, base_probability: float = 0.15):
        self.base_probability = base_probability
        self.chaos_deck = {
            "Environment": [
                "突发天灾 (暴雨/地震/兽潮)",
                "灵气/魔力环境突变 (失效/暴走)",
                "场景崩塌/地形改变"
            ],
            "Character": [
                "盟友突然背叛/反水",
                "关键角色旧伤复发/中毒",
                "路人角色意外介入打乱计划",
                "主角核心装备/能力暂时失效"
            ],
            "Information": [
                "关键情报被证明是错误的",
                "绝密计划被敌人提前知晓",
                "意外得知一个颠覆性的秘密"
            ],
            "Enemy": [
                "第三方势力乱入 (渔翁得利)",
                "宿敌提前登场 (战力碾压)",
                "小怪突然变异/狂暴"
            ]
        }

    def roll_for_chaos(self, current_tension: float) -> Optional[Dict[str, str]]:
        """
        掷骰子决定是否触发混沌事件。
        
        策略：
        - 如果当前 Tension (紧张度) 很低 (<0.4)，增加触发概率 (拒绝平淡)。
        - 如果当前 Tension 极高 (>0.8)，降低触发概率 (避免崩坏，或者触发"意外转机")。
        """
        probability = self.base_probability
        
        if current_tension < 0.4:
            probability += 0.2 # 剧情太平淡，搞点事
        elif current_tension > 0.8:
            probability -= 0.1 # 已经很累了，少搞事
            
        if random.random() < probability:
            return self._draw_card()
            
        return None

    def _draw_card(self) -> Dict[str, str]:
        category = random.choice(list(self.chaos_deck.keys()))
        event = random.choice(self.chaos_deck[category])
        return {
            "type": "Chaos Event",
            "category": category,
            "description": event,
            "instruction": "This is a MANDATORY twist. You must integrate it into the narrative immediately."
        }
