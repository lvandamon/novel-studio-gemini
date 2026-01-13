from typing import List, Dict, Any
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

    def trigger_aggregations(self, chapter_num: int):
        """
        触发分级聚合逻辑 (Fractal Aggregation Trigger)
        由 Archivist 在每章归档后调用。
        
        策略:
        1. Level 1 (Batch-10): 每 10 章触发一次 (10, 20, 30...)
        2. Level 2 (Volume/Batch-100): 每 100 章触发一次 (100, 200...)
        """
        if chapter_num <= 0: return

        # Level 1: 每 10 章聚合一次
        if chapter_num % 10 == 0:
            start = chapter_num - 9
            end = chapter_num
            print(f"🔄 [Summarizer] 触发 L1 聚合 (Ch{start}-{end})...")
            self._aggregate_range(level="batch_10", start=start, end=end, source_level="chapter")

        # Level 2: 每 100 章聚合一次 (基于 Level 1 的摘要)
        if chapter_num % 100 == 0:
            start = chapter_num - 99
            end = chapter_num
            print(f"🔄 [Summarizer] 触发 L2 卷级聚合 (Ch{start}-{end})...")
            self._aggregate_range(level="volume", start=start, end=end, source_level="batch_10")

    def _aggregate_range(self, level: str, start: int, end: int, source_level: str):
        """
        通用聚合函数
        
        Args:
            level: 目标层级 ('batch_10', 'volume')
            start: 起始章节
            end: 结束章节
            source_level: 来源层级 ('chapter', 'batch_10')
        """
        # 1. 获取源摘要文本
        sources_text = self._fetch_source_summaries(source_level, start, end)
        
        if not sources_text:
            print(f"   ⚠️ [Summarizer] {level} 聚合失败: 未找到源摘要 ({start}-{end})")
            return

        # 2. 调用 LLM 生成综述
        try:
            aggregated_content = self.batch_chain.invoke({"summaries": sources_text})
            
            # 3. 存入数据库
            self.memory.save_aggregated_summary(level, start, end, aggregated_content)
            print(f"   ✅ [Summarizer] {level} 聚合完成 ({len(aggregated_content)} 字)")
            
        except Exception as e:
            print(f"   ❌ [Summarizer] 聚合执行出错: {e}")

    def _fetch_source_summaries(self, source_level: str, start: int, end: int) -> str:
        """从数据库抓取并拼接源摘要"""
        buffer = []
        
        if source_level == "chapter":
            # 从 chapters 表抓取
            for i in range(start, end + 1):
                s = self.memory.get_chapter_summary(i)
                if s and s != "暂无摘要。":
                    buffer.append(f"[Ch{i}]: {s}")
                    
        elif source_level == "batch_10":
            # 从 summary_aggregations 表抓取 batch_10
            # 这里的 start/end 是章节号范围
            # 我们需要查找覆盖这个范围的所有 batch_10 记录
            # 假设 batch_10 是严格对齐的 (1-10, 11-20...)
            
            # 获取所有 batch_10，然后筛选 (性能稍差但逻辑简单，考虑到数据量不大)
            all_batches = self.memory.get_aggregated_summaries("batch_10")
            for b in all_batches:
                b_start = b['start']
                b_end = b['end']
                # 检查是否在目标范围内
                if b_start >= start and b_end <= end:
                    buffer.append(f"[阶段 {b_start}-{b_end}]: {b['content']}")
        
        return "\n".join(buffer)

    def generate_summary(self, content: str, chapter_num: int) -> str:
        """(Legacy) 单章摘要生成，保留以备不时之需"""
        summary = self.chain.invoke({"content": content})
        self.memory.update_chapter_summary(chapter_num, summary)
        return summary
