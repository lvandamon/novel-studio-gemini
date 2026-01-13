from typing import List, Dict, Any
import sqlite3
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

        # 🔥 P3修复: 重要事件类型定义
        self.critical_event_types = ["Climax", "Major_Battle", "Death", "Revelation", "Transformation", "Arc_End"]

    def trigger_aggregations(self, chapter_num: int, force_critical: bool = False, critical_reason: str = None):
        """
        🔥 P3升级: 触发分级聚合逻辑 (Fractal Aggregation Trigger)

        策略:
        1. Level 1 (Batch-10): 每 10 章触发一次 (10, 20, 30...)
        2. Level 2 (Volume/Batch-100): 每 100 章触发一次 (100, 200...)
        3. 🔥 P3新增: 重要事件触发额外聚合 (Critical Event Trigger)

        Args:
            chapter_num: 当前章节号
            force_critical: 是否强制触发关键聚合
            critical_reason: 触发原因描述
        """
        if chapter_num <= 0:
            return

        # 🔥 P3新增: 检查是否有重要事件需要立即聚合
        should_critical_aggregate = force_critical or self._check_critical_events(chapter_num)

        if should_critical_aggregate:
            reason = critical_reason or "检测到重要事件"
            print(f"🚨 [Summarizer] 重要事件触发紧急聚合: {reason}")
            self._trigger_critical_aggregation(chapter_num)

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

    def _check_critical_events(self, chapter_num: int) -> bool:
        """
        🔥 P3新增: 检查本章是否包含重要事件

        检测条件:
        1. 事件类型为 Climax/Major_Battle/Death/Revelation
        2. 遥测数据显示 tension >= 85
        3. 有核心伏笔被回收

        Returns:
            bool: 是否需要触发紧急聚合
        """
        try:
            conn = sqlite3.connect(self.memory.db_path)
            cursor = conn.cursor()

            # 检查1: 是否有重要事件
            cursor.execute('''
                SELECT COUNT(*) FROM events
                WHERE chapter_num = ? AND event_type IN (?, ?, ?, ?, ?, ?)
            ''', (chapter_num, *self.critical_event_types))
            critical_event_count = cursor.fetchone()[0]

            if critical_event_count > 0:
                conn.close()
                print(f"   📌 检测到 {critical_event_count} 个关键事件")
                return True

            # 检查2: 遥测数据 tension >= 85
            cursor.execute('''
                SELECT tension FROM chapter_metrics WHERE chapter_num = ?
            ''', (chapter_num,))
            row = cursor.fetchone()
            if row and row[0] and row[0] >= 85:
                conn.close()
                print(f"   📌 检测到高张力章节 (Tension: {row[0]})")
                return True

            # 检查3: 核心伏笔回收
            cursor.execute('''
                SELECT COUNT(*) FROM foreshadowing
                WHERE chapter_resolved = ? AND importance >= 8
            ''', (chapter_num,))
            core_hook_resolved = cursor.fetchone()[0]

            conn.close()

            if core_hook_resolved > 0:
                print(f"   📌 检测到 {core_hook_resolved} 个核心伏笔回收")
                return True

            return False

        except Exception as e:
            print(f"   ⚠️ 重要事件检测失败: {e}")
            return False

    def _trigger_critical_aggregation(self, chapter_num: int):
        """
        🔥 P3新增: 触发关键事件聚合

        策略:
        1. 立即聚合最近5章内容 (mini-batch)
        2. 标记为 'critical' 级别
        3. 在后续 batch_10 聚合时会优先引用
        """
        # 计算范围: 最近5章
        start = max(1, chapter_num - 4)
        end = chapter_num

        print(f"   🔄 [Summarizer] 触发 Critical 聚合 (Ch{start}-{end})...")

        # 获取源摘要
        sources = []
        for i in range(start, end + 1):
            s = self.memory.get_chapter_summary(i)
            if s and s != "暂无摘要。":
                sources.append(f"[Ch{i}]: {s}")

        if not sources:
            print(f"   ⚠️ Critical 聚合失败: 无可用摘要")
            return

        try:
            # 调用 LLM 生成关键综述
            critical_summary = self.batch_chain.invoke({
                "summaries": "\n".join(sources)
            })

            # 存储为 critical 级别
            self.memory.save_aggregated_summary("critical", start, end, critical_summary)
            print(f"   ✅ [Summarizer] Critical 聚合完成 (Ch{start}-{end}, {len(critical_summary)} 字)")

        except Exception as e:
            print(f"   ❌ [Summarizer] Critical 聚合出错: {e}")

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
