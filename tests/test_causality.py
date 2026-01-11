from core.memory import MemoryManager
from core.graph_store import GraphManager
import time

def test_causality():
    print("🕸️ 正在测试事件因果图 (Event Causality DAG)...")
    
    # 初始化
    memory = MemoryManager()
    
    # 检查图谱连接
    if not memory.graph.is_connected():
        print("⚠️ Neo4j 未连接，无法测试图谱因果性。请先启动 Neo4j。")
        return

    # --- 模拟剧情流 ---
    
    print("\n--- 📝 正在生成事件链 ---")
    
    # Ch1: 获得宝物
    e1 = memory.log_event(1, "萧风", "获得宝物", "萧风在后山捡到神秘玉佩。")
    print(f"Event {e1}: 获得玉佩")
    
    # Ch2: 冲突发生 (因 e1 而起)
    e2 = memory.log_event(2, "李四", "挑衅", "李四看到玉佩心生贪念，试图抢夺。", cause_event_id=e1)
    print(f"Event {e2}: 李四抢夺 (Cause: {e1})")
    
    # Ch3: 升级为战斗 (因 e2 而起)
    e3 = memory.log_event(3, "萧风", "击杀", "萧风反击，失手杀死了李四。", cause_event_id=e2)
    print(f"Event {e3}: 萧风杀李四 (Cause: {e2})")
    
    # Ch5: 后果显现 (因 e3 而起)
    e4 = memory.log_event(5, "李家", "通缉", "李家发布追杀令，全城通缉萧风。", cause_event_id=e3)
    print(f"Event {e4}: 李家通缉 (Cause: {e3})")
    
    # --- 验证反向追溯 ---
    
    print("\n--- 🔍 正在反向追溯因果 ---")
    print(f"Query: 为什么发生了事件 {e4} (李家通缉)?")
    
    chain = memory.graph.query_causal_chain(str(e4))
    print(chain)
    
    if "击杀" in chain and "抢夺" in chain:
        print("\n✅ 因果链测试成功！系统成功追踪到了源头。")
    else:
        print("\n❌ 因果链断裂或未找到。")

if __name__ == "__main__":
    test_causality()
