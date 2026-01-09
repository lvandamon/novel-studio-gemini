from core.llm import get_deepseek_chat
from core.prompts import WRITER_GEN_CHAPTER_PROMPT
from langchain_core.output_parsers import StrOutputParser

class WriterAgent:
    def __init__(self):
        self.llm = get_deepseek_chat()
        self.chain = WRITER_GEN_CHAPTER_PROMPT | self.llm | StrOutputParser()

    def write_chapter(self, outline: str, settings: str = "暂无额外设定") -> str:
        """
        调用 V3 模型根据大纲撰写正文
        """
        print("✍️ 作家 (Writer) 正在挥毫泼墨...")
        return self.chain.invoke({
            "outline": outline,
            "settings": settings
        })
