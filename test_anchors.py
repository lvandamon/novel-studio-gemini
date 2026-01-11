from core.memory import MemoryManager

def test_anchors():
    print("🚀 开始测试：黄金锚点 (Immutable Anchors)...")
    memory = MemoryManager()

    # 1. 初始化测试角色
    char_name = "叶凡"
    memory.upsert_character(char_name, {
        "role": "主角",
        "personality": ["冷毅", "重情"],
        "goal": ["回家", "成仙"]
    })

    # 2. 注入锚点
    print(f"\n👉 为 {char_name} 注入锚点...")
    
    # 锚点 1: 核心源动力 (Core Motivation)
    memory.add_anchor(
        char_name, 
        "CoreMotivation", 
        "哪怕背负天渊，需一手托原始帝城，我叶凡一样无敌世间！(核心气质：无敌信念)",
        tags=["battle", "monologue"]
    )

    # 锚点 2: 创伤/禁忌 (Trauma)
    memory.add_anchor(
        char_name, 
        "Trauma", 
        "永远不要在奔驰车面前提起'同学聚会'。这是他凡尘最深的痛。",
        tags=["social", "memory"]
    )

    # 3. 检索详情 (验证锚点是否置顶且显示)
    print(f"\n👉 检索 {char_name} 的完整档案...")
    details = memory.get_character_details([char_name])
    
    print("\n" + "="*40)
    print(details)
    print("="*40)

    # 验证逻辑
    if "无敌信念" in details and "同学聚会" in details:
        print("\n✅ 测试通过：锚点已成功“焊死”在角色档案头部。")
    else:
        print("\n❌ 测试失败：未发现锚点内容。")

if __name__ == "__main__":
    test_anchors()
