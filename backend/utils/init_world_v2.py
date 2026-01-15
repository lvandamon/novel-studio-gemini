from core.memory import MemoryManager
from utils.init_plan import init_plan

def init_world_v2(memory_manager=None):
    memory = memory_manager if memory_manager else MemoryManager()

    # 1. Init Plan
    init_plan(memory)
    
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
    memory.update_chapter_summary(0, "萧风穿越到修仙界，成为青云门资质平平的外门弟子。三年修行，依旧停留在凝气三层。昨日，他在后山捡到一枚神秘的黑色戒指，却无法研究出用途。")

    # 7. Init World Map (GIS Data)
    print("Initializing GIS Map...")
    
    # Locations
    memory.add_location("新手村", "主角出生的平凡小村庄，与世隔绝。", "Wild", "None")
    memory.add_location("青木城", "边陲重镇，修仙者与凡人混居，繁华异常。", "City", "Empire")
    memory.add_location("黑石矿洞", "阴暗潮湿的矿洞，盛产黑铁矿，常有妖兽出没。", "Dungeon", "None")
    memory.add_location("天风城", "帝国西部要塞，驻扎着精锐的狮鹫军团。", "City", "Empire")
    memory.add_location("帝都", "帝国的心脏，皇权与神权交织之地，气势恢宏。", "City", "Empire")
    memory.add_location("云顶天宫", "悬浮于云端之上的神秘宗门，凡人不可视。", "Sect", "Sect")
    memory.add_location("无尽之海港口", "通往海外仙岛的唯一港口，鱼龙混杂。", "City", "Neutral")
    memory.add_location("青云门", "正道大派，坐落于青云山脉，灵气充裕。", "Sect", "Sect")
    memory.add_location("青云门外门广场", "青云门外门弟子活动的区域，宽阔平整。", "Sect", "Sect")

    # Routes (Bidirectional needs explicit entries if directed, but for simplicity we assume logic handles return or add both)
    # Here we simulate the original map
    memory.add_route("新手村", "青木城", 3, {"Walk": "步行", "Carriage": "马车(1天)"})
    memory.add_route("青木城", "新手村", 3, {"Walk": "步行"})
    
    memory.add_route("新手村", "黑石矿洞", 1, {"Walk": "步行"})
    memory.add_route("黑石矿洞", "新手村", 1, {"Walk": "步行"})
    
    memory.add_route("青木城", "天风城", 10, {"Walk": "步行", "Fly": "御剑(2天)"})
    memory.add_route("天风城", "青木城", 10, {"Walk": "步行", "Fly": "御剑(2天)"})
    
    memory.add_route("青木城", "云顶天宫", 30, {"Fly": "御剑(6天)", "Teleport": "传送阵(瞬达)"}, ["Level > 筑基"])
    memory.add_route("云顶天宫", "青木城", 30, {"Fly": "御剑(6天)", "Teleport": "传送阵(瞬达)"})
    
    memory.add_route("青木城", "无尽之海港口", 15, {"Walk": "步行", "Carriage": "灵兽车(5天)"})
    memory.add_route("无尽之海港口", "青木城", 15, {"Walk": "步行"})
    
    memory.add_route("天风城", "帝都", 25, {"Walk": "步行", "Fly": "御剑(5天)", "Teleport": "传送阵(瞬达)"})
    memory.add_route("帝都", "天风城", 25, {"Walk": "步行", "Fly": "御剑(5天)", "Teleport": "传送阵(瞬达)"})

    memory.add_route("帝都", "云顶天宫", 15, {"Fly": "御剑(3天)", "Teleport": "传送阵(瞬达)"})
    memory.add_route("云顶天宫", "帝都", 15, {"Fly": "御剑(3天)", "Teleport": "传送阵(瞬达)"})
    
    # 增加青云门相关路线
    memory.add_route("青木城", "青云门", 5, {"Walk": "步行", "Fly": "御剑(1天)"})
    memory.add_route("青云门", "青木城", 5, {"Walk": "步行", "Fly": "御剑(1天)"})
    
    memory.add_route("青云门", "青云门外门广场", 0, {"Walk": "步行(0.1天)"})
    memory.add_route("青云门外门广场", "青云门", 0, {"Walk": "步行(0.1天)"})


    print("🎉 World V2 Initialized!")

if __name__ == "__main__":
    init_world_v2()
