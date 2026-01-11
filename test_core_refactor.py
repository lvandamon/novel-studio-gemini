from core.memory import MemoryManager
from core.schemas import CharacterSchema, RealityLayer, GraphTripletSchema
import uuid

def test_memory_identity():
    print("\n🧪 --- 测试 1: 身份与马甲 (Identity & Aliases) ---")
    m = MemoryManager(db_path="data/test_refactor.db", vector_db_path="data/test_refactor_vec")
    
    # 1. 创建本尊
    print("Step 1: 创建 '韩立'")
    m.upsert_character("韩立", {"role": "主角", "level": "炼气期"})
    
    char = m.get_character("韩立")
    uid = char['id']
    print(f"   -> 韩立 ID: {uid}")
    assert char['level'] == "炼气期"

    # 2. 马甲更新 (自动关联)
    # 注意：在新的逻辑里，如果我直接 upsert "韩跑跑"，而没有先注册别名，它会创建一个新角色。
    # 必须先告诉系统 "韩跑跑" 是 "韩立" 的别名，或者在 upsert "韩立" 时带上 aliases 列表。
    # 让我们测试 "智能合并"：如果我们明确更新 "韩立" 并添加别名
    print("Step 2: 韩立获得别名 '韩跑跑'")
    m.upsert_character("韩立", {"aliases": ["韩跑跑"]})
    
    # 3. 使用马甲更新数据
    print("Step 3: '韩跑跑' 升级了 (别名更新)")
    m.upsert_character("韩跑跑", {"level": "筑基期"})
    
    # 4. 验证
    char_origin = m.get_character("韩立")
    char_alias = m.get_character("韩跑跑")
    
    print(f"   -> 韩立 Level: {char_origin['level']}")
    print(f"   -> 韩跑跑 ID: {char_alias['id']}")
    
    assert char_origin['id'] == char_alias['id'], "ID 不匹配！马甲机制失效！"
    assert char_origin['level'] == "筑基期", "数据未同步！"
    print("✅ 身份系统测试通过！")

def test_graph_logic():
    print("\n🧪 --- 测试 2: 图谱关系管理 (Graph Relations) ---")
    m = MemoryManager(db_path="data/test_refactor.db", vector_db_path="data/test_refactor_vec")
    
    if not m.graph.is_connected():
        print("⚠️ Neo4j 未连接，跳过图谱测试。\n")
        return

    src = "测试A"
    tgt = "测试B"
    
    # 1. 建立朋友关系
    print("Step 1: 建立朋友关系")
    m.graph.update_relationship(src, "Character", "FRIEND", tgt, "Character")
    context = m.graph.query_entity_context(src)
    print(f"   -> Context: {context}")
    assert "FRIEND" in context

    # 2. 关系破裂 (删除朋友)
    print("Step 2: 删除朋友关系")
    m.graph.update_relationship(src, "Character", "FRIEND", tgt, "Character", is_negated=True)
    context = m.graph.query_entity_context(src)
    print(f"   -> Context: {context}")
    # 注意：query_entity_context 返回的是文本，如果没有关系可能返回"暂无..."
    assert "FRIEND" not in context

    # 3. 建立死敌关系
    print("Step 3: 建立死敌关系")
    m.graph.update_relationship(src, "Character", "ENEMY", tgt, "Character")
    context = m.graph.query_entity_context(src)
    print(f"   -> Context: {context}")
    assert "ENEMY" in context
    print("✅ 图谱逻辑测试通过！")

if __name__ == "__main__":
    try:
        test_memory_identity()
        test_graph_logic()
        print("\n🎉 所有核心测试通过！")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        exit(1)
