from core.memory import MemoryManager
from core.chaos import ChaosEngine

def test_chaos_cooldown():
    print("🚀 开始测试：Chaos Engine v2 (冷却机制)...")
    memory = MemoryManager()
    
    # 必须传入 memory 实例
    chaos = ChaosEngine(memory, base_probability=1.0) # 100% 触发以便测试
    
    print("\n--- Round 1: 第 10 章 (Tension 0.2 - 低谷期) ---")
    # 强制触发一次
    event1 = chaos.roll_for_chaos(current_chapter=10, current_tension=0.2)
    if event1:
        print(f"✅ 触发事件: [{event1['category']}] {event1['description']}")
        cat1 = event1['category']
    else:
        print("❌ 未触发 (不应发生)")
        return

    print(f"\n--- Round 2: 第 12 章 (尝试触发相同类别) ---")
    # 此时 cat1 应该在冷却中
    # 我们模拟多次尝试，看看能不能再次随到 cat1 (理论上 ChaosEngine 内部会过滤掉 cat1)
    
    # 为了验证，我们直接检查 active cooldowns
    active = memory.get_active_cooldowns(current_chapter=12)
    print(f"🧊 当前冷却池 (Ch12): {active}")
    
    if cat1 in active:
        print("✅ 验证通过: 类别已被冻结。")
    else:
        print(f"❌ 验证失败: {cat1} 未在冷却池中。")
        
    print("\n--- Round 3: 第 30 章 (冷却过期后) ---")
    active_future = memory.get_active_cooldowns(current_chapter=30)
    print(f"🧊 当前冷却池 (Ch30): {active_future}")
    if cat1 not in active_future:
         print("✅ 验证通过: 冷却已自然解除。")
    else:
         print(f"❌ 验证失败: {cat1} 仍未解冻。")

if __name__ == "__main__":
    test_chaos_cooldown()
