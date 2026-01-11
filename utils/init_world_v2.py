from core.memory import MemoryManager
from utils.init_plan import init_plan

def init_world_v2():
    # 1. Init Plan
    init_plan()
    
    memory = MemoryManager()
    
    print("\nInitializing Characters for V2 Test...")
    
    # 2. Init Protagonist: 萧风
    memory.upsert_character("萧风", {
        "role": "主角",
        "level": "凝气三层",
        "location": "青云门外门广场",
        "importance": "Protagonist",
        "personality": ["隐忍", "谨慎", "重情义"],
        "values": ["人不犯我我不犯人", "滴水之恩涌泉相报"], # Simulator will use this
        "psychological_state": "焦虑",
        "current_state": "正常",
        "goals": ["筑基", "活下去"],
        "inventory": ["铁剑", "神秘黑戒(未激活)", "下品灵石x5"],
        "psychological_history": [
            {"chapter": 0, "state": "焦虑", "reason": "大比在即，修为停滞不前"}
        ]
    })
    
    # 3. Init Major Character: 林月
    memory.upsert_character("林月", {
        "role": "外门大师姐",
        "level": "凝气八层",
        "location": "青云门外门广场",
        "importance": "Major",
        "personality": ["高冷", "护短", "傲娇"],
        "values": ["守护宗门荣誉", "强者为尊"],
        "psychological_state": "自信",
        "current_state": "正常",
        "goals": ["突破筑基", "整顿外门风气"],
        "relationships": {"萧风": "看好的师弟"}
    })
    
    # 4. Init Antagonist: 赵虎
    memory.upsert_character("赵虎", {
        "role": "外门恶霸",
        "level": "凝气五层",
        "location": "青云门外门广场",
        "importance": "Minor",
        "personality": ["残忍", "欺软怕硬", "贪婪"],
        "values": ["弱肉强食", "利益至上"],
        "psychological_state": "嚣张",
        "current_state": "正常",
        "relationships": {"萧风": "欺凌对象"}
    })
    
    # 5. Set Narrative Focus
    memory.update_narrative_focus(
        volume="第一卷 云州往事",
        arc="青云惊变",
        beat="铺垫",
        goal="展示萧风在外门的艰难处境",
        conflict="赵虎的挑衅",
        state="青云门外门大比即将开始，气氛紧张。",
        current_date="天道历元年5月20日"
    )
    
    # 6. Set Previous Summary (Chapter 0)
    memory.update_chapter_summary(0, "萧风穿越到修仙界，成为青云门资质平平的外门弟子。三年修行，依旧停留在凝气三层。昨日，他在后山捡到一枚神秘的黑色戒指，却无法研究出用途。 সন")

    print("🎉 World V2 Initialized!")

if __name__ == "__main__":
    init_world_v2()
