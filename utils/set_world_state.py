import sys
import os

# 将项目根目录加入 python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.memory import MemoryManager

def main():
    print("🚀 正在连接海马体 (Memory System)...")
    mem = MemoryManager()
    
    # 1. 查看旧状态
    old_state = mem.get_narrative_focus()
    print(f"📉 [旧状态]: {old_state.get('volume', 'N/A')} - {old_state.get('arc', 'N/A')}")
    
    # 2. 注入新状态
    print("\n💉 正在注入第一卷核心指令...")
    mem.update_narrative_focus(
        volume="第一卷：云起龙骧",
        arc="第一单元：外门风云",
        beat="铺垫 (Setup) - 展示主角困境",
        goal="通过外门考核，避免被逐出宗门",
        conflict="资质低劣，且被执事弟子针对。资源匮乏。",
        state="修仙界灵气开始复苏，各大宗门争夺资源。凡人界战乱频发。"
    )
    
    # 3. 验证
    new_state = mem.get_narrative_focus()
    print(f"📈 [新状态]: {new_state['volume']}")
    print(f"   - 单元: {new_state['arc']}")
    print(f"   - 节拍: {new_state['beat']}")
    print(f"   - 目标: {new_state['goal']}")
    print(f"   - 冲突: {new_state['conflict']}")
    print("\n✅ 全局状态已固化。Agent 现在拥有了“节拍”意识。")

if __name__ == "__main__":
    main()

