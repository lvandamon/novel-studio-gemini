import random
from typing import Optional, Dict
from core.memory import MemoryManager

class ChaosEngine:
    """
    熵增引擎 v2.0 (With Cooldown & Tension Awareness)
    
    不再是瞎掷骰子，而是一个有节奏的“意外生成器”。
    """
    
    def __init__(self, memory_manager: MemoryManager, base_probability: float = 0.15):
        self.memory = memory_manager
        self.base_probability = base_probability
        
        # 定义各类别的冷却时间 (章数)
        # 越严重的灾难，冷却时间越长
        self.cooldown_rules = {
            "Environment": 15,  # 天灾不常有
            "Character": 10,    # 背叛不能太频繁
            "Information": 5,   # 信息反转可以稍多点
            "Enemy": 8          # 乱入适中
        }
        
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

    def roll_for_chaos(self, current_chapter: int, current_tension: float) -> Optional[Dict[str, str]]:
        """
        根据当前章数和紧张度，决定是否触发意外。
        """
        
        # 1. 检查冷却池 (Global Cooldown Check)
        frozen_categories = self.memory.get_active_cooldowns(current_chapter)
        available_categories = [cat for cat in self.chaos_deck.keys() if cat not in frozen_categories]
        
        if not available_categories:
            # 所有灾难都在冷却中，天下太平
            return None

        # 2. 动态概率调整 (Dynamic Probability based on Tension)
        # Tension (0.0 - 1.0)
        # 逻辑：
        # - Tension > 0.8 (高潮期): 降低干扰概率，让读者专注于当前的高潮，除非是"Mechanic Failure"
        # - Tension < 0.3 (平淡期): 大幅提升概率，"起风了"
        
        probability = self.base_probability
        
        if current_tension > 0.8:
            probability *= 0.2 # 极大幅度降低，高潮不容打断
            # print(f"   🛡️ 高潮保护机制启动 (Tension={current_tension}), 意外概率降至 {probability:.2f}")
        elif current_tension < 0.3:
            probability *= 2.5 # 提升，以此打破沉闷
            # print(f"   🔥 剧情催化机制启动 (Tension={current_tension}), 意外概率升至 {probability:.2f}")
        else:
            # 中间态，微调
            pass

        # 3. 掷骰子
        if random.random() < probability:
            return self._trigger_event(available_categories, current_chapter)
            
        return None

    def _trigger_event(self, available_categories: list, current_chapter: int) -> Dict[str, str]:
        # 随机抽取一个可用的类别
        category = random.choice(available_categories)
        event_desc = random.choice(self.chaos_deck[category])
        
        # 设定冷却
        duration = self.cooldown_rules.get(category, 10)
        self.memory.set_chaos_cooldown(category, current_chapter, duration)
        
        return {
            "type": "Chaos Event",
            "category": category,
            "description": event_desc,
            "instruction": f"Chaos triggered! You MUST integrate this event. Next similar event is frozen for {duration} chapters."
        }