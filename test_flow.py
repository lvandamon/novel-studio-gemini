import os
import json
from dotenv import load_dotenv
from agents.editor_agent import EditorAgent
from agents.writer_agent import WriterAgent
from agents.reviewer_agent import ReviewerAgent
from agents.archivist_agent import ArchivistAgent
from agents.foreshadowing_agent import ForeshadowingAgent
from core.memory import MemoryManager
from core.context_manager import ContextManager

def print_step(title):
    print(f"\n{'='*20} {title} {'='*20}")

def main():
    load_dotenv()
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("❌ 错误: 请先在 .env 中配置 DEEPSEEK_API_KEY")
        return

    # 0. 初始化
    print_step("初始化核心系统")
    memory = MemoryManager()
    context_manager = ContextManager(memory)
    
    # 按照 Agent 定义传递 memory_manager
    editor = EditorAgent()
    writer = WriterAgent()
    reviewer = ReviewerAgent(memory) 
    archivist = ArchivistAgent(memory)
    hook_hunter = ForeshadowingAgent(memory)

    # 1. 注入模拟数据 (如果数据库是空的)
    print("🧠 正在注入基础人设与世界观...")
    memory.upsert_character("萧风", {
        "role": "主角",
        "personality": "冷静、果断、内敛",
        "status": "外门弟子，修为练气三层",
        "goal": "查明家族被灭真相",
        "description": "面容清秀但目光如刀，惯穿一件洗得发白的青衫。"
    })
    memory.upsert_character("赵猛", {
        "role": "反派/小人",
        "personality": "嚣张、跋扈、记仇",
        "status": "外门执事弟子，修为练气五层",
        "description": "身材魁梧，左脸有一道刀疤。"
    })

    # 模拟一条关键历史记忆：灭门惨案
    memory.log_event(1, "萧风", "backstory", "萧家一夜之间被蒙面人血洗，萧风躲在井底目睹了领头者右手虎口处的火焰刺青。")
    
    # 2. 生成大纲
    chapter_num = 2
    prev_summary = "萧风通过了入门考核，但因为资质平庸，被分配到了最脏最累的后山矿区。赵猛一直对他虎视眈眈。"
    
    print_step(f"第一步：主编制定第 {chapter_num} 章大纲")
    # 使用 ContextManager 组装主编上下文
    editor_context = context_manager.build_editor_context(chapter_num, prev_summary)
    
    # EditorAgent.generate_outline 已经内置了 JSON 解析
    outline_data = editor.generate_outline(editor_context, chapter_num)
    
    print(f"📜 大纲锁定: {outline_data.get('title', '未命名')}")
    print(f"🎯 叙事重心: {outline_data.get('narrative_focus', '未定义')}")

    # 3. 撰写正文
    print_step("第二步：作家挥毫撰写正文")
    # 组装作家上下文
    writer_context = context_manager.build_writer_context(
        str(outline_data['outline']), 
        outline_data['active_characters']
    )
    
    content = writer.write_chapter(str(outline_data['outline']), writer_context)
    print(f"✍️ 正文撰写完毕，共 {len(content)} 字。")
    print("-" * 40)
    # 展示前 300 字，看看“清风揽岳”的文风
    print(content[:600] + "...") 
    print("-" * 40)

    # 4. 审核
    print_step("第三步：书评人逻辑校验")
    # ReviewerAgent.review_draft 内部会自动执行混合检索
    feedback = reviewer.review_draft(content)
    print(f"🧐 审核意见: {feedback}")

    # 5. 归档与伏笔分析 (只有 PASS 或简单测试时执行)
    print_step("第四步：数据归档与记忆固化")
    
    # 归档 (提取新设定和事件，内部已包含 add_chapter_context)
    archivist.archive_chapter(content, chapter_num)
    
    # 伏笔分析
    hook_hunter.analyze_hooks(content, chapter_num)
    
    # 模拟摘要存储
    memory.update_chapter_summary(chapter_num, "萧风在矿区遭遇赵猛寻衅，关键时刻，九龙鼎产生异动，萧风借机反制并埋下实力的伏笔。")
    
    print(f"✅ 第 {chapter_num} 章已全流程闭合处理完毕。")

if __name__ == "__main__":
    main()
