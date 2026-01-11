from core.memory import MemoryManager
import sys

def init_style_data():
    memory = MemoryManager()
    
    print("🖋️ 正在初始化 Style Guide (文风样板)...")
    
    # 1. 战斗描写 (Action)
    memory.add_style_sample(
        category="Action",
        content="""萧风没有废话，手中青钢剑骤然出鞘。
铮！
一道寒光如匹练般划破夜空。空气中爆出一团肉眼可见的气浪，那是灵气被瞬间压缩后的激荡。
这一剑，快到了极致，也狠到了极致。没有花哨的剑招，只有最纯粹的速度与力量。
“太慢了。”萧风冷哼一声，身形在空中留下一道残影，瞬间欺身而上。""",
        notes="强调速度感、声音描写、灵气特效，以及主角的冷酷。"
    )
    
    # 2. 环境描写 (Scenery)
    memory.add_style_sample(
        category="Scenery",
        content="""残阳如血，将断壁残垣染成了一片暗红。
风中夹杂着浓重的血腥味和焦糊味，原本繁华的宗门广场，此刻只剩下满地的碎石和尚未干涸的血迹。
几只黑鸦落在枯树上，发出嘶哑的鸣叫，仿佛在嘲笑这世间的无常。
萧风站在废墟之上，长袍被风吹得猎猎作响，背影显得无比萧瑟。""",
        notes="环境烘托心境，使用颜色（血红、暗红）、声音（鸦鸣、风声）来营造压抑感。"
    )

    # 3. 对话与装逼 (Dialogue)
    memory.add_style_sample(
        category="Dialogue",
        content="""老者眯起眼睛，周身威压缓缓释放，冷声道：“年轻人，过刚易折。只要你交出那件东西，老夫保你全尸。”
萧风嘴角勾起一抹讥讽的弧度，轻轻弹了弹剑身：“想要？那就拿命来换。”
“冥顽不灵！”
“我的道，不需要向任何人低头。哪怕是天王老子来了，也要问问我手中的剑答不答应。”""",
        notes="反派要给压力，主角要从容反击。对话要短促有力，体现主角的道心。"
    )

    # 4. 心理活动 (Inner Monologue)
    memory.add_style_sample(
        category="InnerMonologue",
        content="""（虽然他表面平静，但内心早已掀起惊涛骇浪。）
这股气息...绝对错不了！是那个人的功法！
萧风握剑的手指因为用力过度而微微发白。十年的隐忍，十年的苟活，不就是为了这一刻吗？
不能急，绝对不能急。一旦暴露身份，之前的努力就全白费了。""",
        notes="心理描写要通过肢体动作（握剑发白）来侧面表现，不要全是独白。"
    )

    print("✅ 文风样板录入完成。")
    
    # --- 验证测试 ---
    print("\n🔍 正在进行检索测试 (Random Sampling)...")
    
    # 抽取 2 个样本
    style_context = memory.get_style_examples(limit=2)
    print(style_context)

if __name__ == "__main__":
    init_style_data()
