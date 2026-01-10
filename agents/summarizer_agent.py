from core.llm import get_deepseek_chat
from core.prompts import SUMMARIZER_EXECUTE_PROMPT
from core.memory import MemoryManager
from langchain_core.output_parsers import StrOutputParser

class SummarizerAgent:
    def __init__(self, memory_manager: MemoryManager):
        self.llm = get_deepseek_chat()
        self.chain = SUMMARIZER_EXECUTE_PROMPT | self.llm | StrOutputParser()
        self.memory = memory_manager

    def generate_summary(self, content: str, chapter_num: int) -> str:
        """生成并保存摘要"""
        print(f"📝 摘要助手 (Summarizer) 正在阅读第 {chapter_num} 章...")
        summary = self.chain.invoke({"content": content})
        
        # 存入数据库
        self.memory.update_chapter_summary(chapter_num, summary)
        print(f"   -> 摘要已生成 ({len(summary)} 字)")
        return summary
