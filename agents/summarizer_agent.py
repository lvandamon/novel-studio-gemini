from core.llm import get_deepseek_chat
from core.prompts import SUMMARIZER_EXECUTE_PROMPT, SUMMARIZER_BATCH_PROMPT
from core.memory import MemoryManager
from langchain_core.output_parsers import StrOutputParser

class SummarizerAgent:
    def __init__(self, memory_manager: MemoryManager):
        self.llm = get_deepseek_chat()
        self.chain = SUMMARIZER_EXECUTE_PROMPT | self.llm | StrOutputParser()
        self.batch_chain = SUMMARIZER_BATCH_PROMPT | self.llm | StrOutputParser()
        self.memory = memory_manager

    def generate_summary(self, content: str, chapter_num: int) -> str:
        """生成并保存摘要"""
        print(f"📝 摘要助手 (Summarizer) 正在阅读第 {chapter_num} 章...")
        summary = self.chain.invoke({"content": content})
        
        # 存入数据库
        self.memory.update_chapter_summary(chapter_num, summary)
        print(f"   -> 摘要已生成 ({len(summary)} 字)")
        
        # 自动触发批量摘要 (Every 10 chapters)
        if chapter_num > 0 and chapter_num % 10 == 0:
            start_chap = chapter_num - 9
            self.generate_batch_summary(start_chap, chapter_num, level="batch_10")
            
        return summary

    def generate_batch_summary(self, start_chapter: int, end_chapter: int, level: str = "batch_10") -> str:
        """生成批量/阶段性摘要"""
        print(f"📚 正在生成阶段性综述 ({start_chapter}-{end_chapter})...")
        
        # 1. 获取原始摘要
        summaries_text = ""
        for i in range(start_chapter, end_chapter + 1):
            s = self.memory.get_chapter_summary(i)
            summaries_text += f"Ch{i}: {s}\n"
            
        if not summaries_text.strip():
            print("   -> 无有效摘要，跳过聚合。")
            return ""

        # 2. 生成聚合摘要
        aggregated_summary = self.batch_chain.invoke({"summaries": summaries_text})
        
        # 3. 存入数据库
        self.memory.save_aggregated_summary(level, start_chapter, end_chapter, aggregated_summary)
        print(f"   -> 阶段综述已归档 ({len(aggregated_summary)} 字)")
        return aggregated_summary
