from core.llm import get_deepseek_reasoner
from core.prompts import EDITOR_GEN_OUTLINE_PROMPT
from langchain_core.output_parsers import StrOutputParser

class EditorAgent:
    def __init__(self):
        self.llm = get_deepseek_reasoner()
        self.chain = EDITOR_GEN_OUTLINE_PROMPT | self.llm | StrOutputParser()

    def generate_outline(self, summary: str, context: str, chapter_num: int) -> str:
        """
        调用 R1 模型生成章节大纲
        """
        print(f"🕵️‍♂️ 主编 (Editor) 正在思考第 {chapter_num} 章大纲...")
        return self.chain.invoke({
            "summary": summary,
            "context": context,
            "chapter_num": chapter_num
        })
