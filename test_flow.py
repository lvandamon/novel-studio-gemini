from agents.editor_agent import EditorAgent
from agents.writer_agent import WriterAgent
import os
from dotenv import load_dotenv

def main():
    load_dotenv()
    
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("❌ 错误: 未找到 DEEPSEEK_API_KEY，请检查 .env 文件ảng")
        return

    # 1. 模拟输入数据
    summary = "主角林风在青云门外门大比中意外击败了内门弟子王虎，引起了长老关注，但也得罪了王虎的哥哥王龙。"
    context = "林风回到破旧的小屋，检查战利品，发现王虎储物袋里有一枚神秘的黑色玉简。"
    chapter_num = 12

    # 2. 初始化智能体
    editor = EditorAgent()
    writer = WriterAgent()

    # 3. 主编生成大纲
    print("--- 1. 主编阶段 ---")
    outline = editor.generate_outline(summary, context, chapter_num)
    print("\n📜 [大纲内容]:\n")
    print(outline)
    print("\n" + "="*50 + "\n")

    # 4. 作家撰写正文
    print("--- 2. 作家阶段 ---")
    # 模拟检索到的设定（暂时硬编码）
    settings = "【物品设定】黑色玉简：上古魔修传承，需滴血认主。\n【人物设定】林风：性格隐忍坚毅，修习《长春功》。"
    
    content = writer.write_chapter(outline, settings)
    print("\n📝 [正文内容]:\n")
    print(content)

if __name__ == "__main__":
    main()

