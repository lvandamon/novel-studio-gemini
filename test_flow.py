import os
import time
from dotenv import load_dotenv
from agents.editor_agent import EditorAgent
from agents.writer_agent import WriterAgent
from agents.reviewer_agent import ReviewerAgent
from agents.archivist_agent import ArchivistAgent
from core.memory import MemoryManager

def print_step(title):
    print(f"\n{'='*20} {title} {'='*20}")

def main():
    load_dotenv()
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("❌ 错误: 请先在 .env 中配置 DEEPSEEK_API_KEY")
        return

    # 0. 初始化
    print_step("初始化系统")
    memory = MemoryManager()
    editor = EditorAgent()
    writer = WriterAgent()
    reviewer = ReviewerAgent(memory)
    archivist = ArchivistAgent(memory)

    # 模拟写入一段历史记忆（为了测试一致性检查）
    print("🧠 注入历史设定...")
    memory.add_chapter_context(
        "林风的传家宝是【九龙鼎】，由于鼎身破损，目前只能用来炼制最基础的气血丹。", 
        chapter_num=1
    )

    # 输入参数
    chapter_num = 13
    summary = "林风在废墟中发现了一枚古怪的符文。"
    context = "深夜，林风正在破庙中休息，九龙鼎悬浮在身前。"

    # 1. 生成大纲
    print_step(f"第一步：主编制定第 {chapter_num} 章大纲")
    outline = editor.generate_outline(summary, context, chapter_num)
    print(f"📜 大纲生成完毕，字数: {len(outline)}")
    
    # 2. 撰写与审核循环
    print_step("第二步：作家撰写与书评人审核")
    max_retries = 2
    current_content = ""
    
    # 获取当前角色设定
    settings = memory.get_all_characters_summary()

    for attempt in range(max_retries + 1):
        print(f"✍️ 作家开始创作 (尝试第 {attempt + 1} 次)...")
        # 如果是重写，将建议加入到 settings 中提示作家
        current_content = writer.write_chapter(outline, settings)
        
        print("🧐 书评人介入审核...")
        feedback = reviewer.review_draft(current_content)
        
        if "PASS" in feedback.upper():
            print("✅ 审核通过！正文质量符合要求。")
            break
        else:
            print(f"⚠️ 审核未通过！意见如下：\n{feedback}")
            if attempt < max_retries:
                print("🔄 准备根据意见进行重写...")
                # 将反馈作为临时设定传给下一次写作
                settings += f"\n\n【修改建议】：{feedback}"
            else:
                print("🚨 已达到最大重试次数，保留当前版本。 ולא")

    # 3. 归档
    print_step("第三步：档案员处理")
    archivist.archive_chapter(current_content, chapter_num)

    # 4. 验证结果
    print_step("任务完成")
    print(f"✅ 第 {chapter_num} 章已存入向量库。")
    print("🔍 检索测试（查询：九龙鼎）：")
    search_res = memory.query_related_context("九龙鼎")
    print(search_res)

if __name__ == "__main__":
    main()
