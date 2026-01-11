from core.memory import MemoryManager
import random

def mock_telemetry_data():
    print("🚀 模拟生成遥测数据 (Mock Telemetry Data)...")
    memory = MemoryManager()
    
    # 模拟生成 50 章的数据，展现一个“崩坏”的过程
    for i in range(1, 51):
        # 前 20 章：高质量
        if i <= 20:
            tension = random.randint(40, 70)
            darkness = random.randint(30, 60)
            logic = random.randint(90, 100)
            consist = random.randint(90, 100)
            critique = "PASS"
        # 20-40 章：开始注水
        elif i <= 40:
            tension = random.randint(20, 40) # 紧张感下降
            darkness = random.randint(10, 30) # 氛围变轻
            logic = random.randint(70, 90)
            consist = random.randint(80, 90)
            critique = "节奏拖沓，建议加速。"
        # 40-50 章：战力崩坏
        else:
            tension = random.randint(80, 100) # 强行拉高紧张感
            darkness = random.randint(80, 100) # 黑化
            logic = random.randint(40, 60) # 逻辑崩盘
            consist = random.randint(30, 50) # 人设 OOC
            critique = "战力体系崩溃，主角性格严重分裂！"

        metrics = {
            "tension": tension,
            "tone_darkness": darkness,
            "pacing_score": random.randint(40, 60),
            "character_consistency_score": consist,
            "plot_logic_score": logic,
            "critique": critique
        }
        
        memory.log_chapter_metrics(i, metrics)
        
    print("✅ 50 章模拟数据已写入。请运行 Streamlit 查看仪表盘。")
    print("👉 命令: uv run streamlit run app.py")

if __name__ == "__main__":
    mock_telemetry_data()