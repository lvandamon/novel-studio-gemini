from core.memory import MemoryManager
import sys

def init_bible_data():
    memory = MemoryManager()
    
    print("📖 正在初始化 World Bible (世界圣经)...")
    
    # 1. 魔法体系公理
    memory.add_bible_entry(
        category="MagicSystem",
        topic="灵气守恒定律",
        content="凡人修仙，逆天而行。吸纳天地灵气必须付出代价。强行突破境界若无丹药护体，必遭天道反噬，轻则经脉尽断，重则身死道消。灵力不可凭空产生，施展法术消耗的是自身的精气神。"
    )
    
    memory.add_bible_entry(
        category="MagicSystem",
        topic="五行生克",
        content="金生水，水生木，木生火，火生土，土生金。金克木，木克土，土克水，水克火，火克金。同境界下，属性克制可提升30%的威力压制。逆属性强行施法，消耗加倍。"
    )

    # 2. 世界背景公理
    memory.add_bible_entry(
        category="WorldHistory",
        topic="天魔之乱",
        content="三千年前，域外天魔降临九州，造成修真界断代。所有化神期以上的大能全部陨落或飞升。如今九州灵气稀薄，元婴期已是一方霸主，化神期只存在于传说中。"
    )

    # 3. 主角核心设定 (绝对不可变)
    memory.add_bible_entry(
        category="CharacterCore",
        topic="萧风_复仇",
        content="萧风的家族在十年前被【血煞宗】灭门，原因是家族守护的一块【古朴玉佩】。萧风发誓要灭掉血煞宗满门。这个仇恨是他行动的根本动力，无论何时何地，只要听到血煞宗的消息，他都会失去理智。"
    )

    print("✅ 基础公理录入完成。")
    
    # --- 验证测试 ---
    print("\n🔍 正在进行检索测试...")
    
    # 测试 1: 场景涉及萧风和战斗
    context = memory.get_bible_context(
        query="萧风遇到了一个血煞宗的弟子，准备战斗。",
        active_entities=["萧风"]
    )
    print("--- Test Case 1: 萧风 vs 血煞宗 ---")
    print(context)
    
    # 测试 2: 场景涉及修炼突破
    context = memory.get_bible_context(
        query="主角试图强行突破到筑基期，但是没有丹药。",
        active_entities=["萧风"]
    )
    print("\n--- Test Case 2: 强行突破 ---")
    print(context)

if __name__ == "__main__":
    init_bible_data()
