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

        # 🔥 P4新增: 灵活聚合配置
        self.aggregation_config = {
            "base_batch_size": 10,       # 基础批次大小
            "min_batch_size": 5,         # 最小批次大小
            "max_batch_size": 15,        # 最大批次大小
            "volume_batch_count": 10,    # 每卷包含的批次数
            "adaptive_mode": True        # 是否启用自适应模式
        }

        # 🔥 P4新增: 单元(Arc)边界追踪
        self._arc_boundaries: List[int] = []
        self._last_arc_chapter: int = 0

    def trigger_aggregations(self, chapter_num: int, force_critical: bool = False,
                              critical_reason: str = None, arc_ended: bool = False,
                              arc_name: str = None):
        """
        🔥 P3升级 + P4升级: 触发分级聚合逻辑 (Fractal Aggregation Trigger)

        策略:
        1. Level 1 (Batch): 每 N 章触发一次 (N可配置,默认10)
        2. Level 2 (Volume): 每 M 个Batch触发一次
        3. 🔥 P3新增: 重要事件触发额外聚合 (Critical Event Trigger)
        4. 🔥 P4新增: 单元(Arc)边界触发聚合
        5. 🔥 P4新增: 自适应批次大小

        Args:
            chapter_num: 当前章节号
            force_critical: 是否强制触发关键聚合
            critical_reason: 触发原因描述
            arc_ended: 是否为单元结束点
            arc_name: 结束的单元名称
        """
        if chapter_num <= 0:
            return

        batch_size = self._get_adaptive_batch_size(chapter_num)

        # 🔥 P4新增: 单元(Arc)结束触发聚合
        if arc_ended:
            print(f"📚 [Summarizer] 单元结束触发聚合: {arc_name}")
            self._trigger_arc_boundary_aggregation(chapter_num, arc_name)
            self._arc_boundaries.append(chapter_num)
            self._last_arc_chapter = chapter_num

        # 🔥 P3新增: 检查是否有重要事件需要立即聚合
        should_critical_aggregate = force_critical or self._check_critical_events(chapter_num)

        if should_critical_aggregate:
            reason = critical_reason or "检测到重要事件"
            print(f"🚨 [Summarizer] 重要事件触发紧急聚合: {reason}")
            self._trigger_critical_aggregation(chapter_num)

        # Level 1: 基于自适应批次大小聚合
        if self._should_trigger_batch_aggregation(chapter_num, batch_size):
            start = self._calculate_batch_start(chapter_num, batch_size)
            end = chapter_num
            print(f"🔄 [Summarizer] 触发 L1 聚合 (Ch{start}-{end}, batch_size={batch_size})...")
            self._aggregate_range(level="batch_10", start=start, end=end, source_level="chapter")

        # Level 2: 基于批次数量聚合
        if self._should_trigger_volume_aggregation(chapter_num):
            start = self._calculate_volume_start(chapter_num)
            end = chapter_num
            print(f"🔄 [Summarizer] 触发 L2 卷级聚合 (Ch{start}-{end})...")
            self._aggregate_range(level="volume", start=start, end=end, source_level="batch_10")

    def _get_adaptive_batch_size(self, chapter_num: int) -> int:
        """
        🔥 P4新增: 获取自适应批次大小

        策略:
        - 前50章: 较小批次 (5章) - 便于细粒度回顾
        - 50-200章: 标准批次 (10章)
        - 200章+: 可以稍大批次 (12-15章)
        """
        if not self.aggregation_config["adaptive_mode"]:
            return self.aggregation_config["base_batch_size"]

        if chapter_num <= 50:
            return self.aggregation_config["min_batch_size"]
        elif chapter_num <= 200:
            return self.aggregation_config["base_batch_size"]
        else:
            # 渐进增大,但不超过最大值
            extra = min((chapter_num - 200) // 100, 5)
            return min(
                self.aggregation_config["base_batch_size"] + extra,
                self.aggregation_config["max_batch_size"]
            )

    def _should_trigger_batch_aggregation(self, chapter_num: int, batch_size: int) -> bool:
        """
        🔥 P4新增: 判断是否应该触发批次聚合

        考虑因素:
        1. 章节数是否达到批次边界
        2. 是否刚经过单元(Arc)边界
        """
        # 标准批次边界
        if chapter_num % batch_size == 0:
            return True

        # 检查是否在单元边界后的合适位置
        if self._arc_boundaries:
            last_arc = self._arc_boundaries[-1]
            chapters_since_arc = chapter_num - last_arc
            if chapters_since_arc >= batch_size:
                return True

        return False

    def _should_trigger_volume_aggregation(self, chapter_num: int) -> bool:
        """🔥 P4新增: 判断是否应该触发卷级聚合"""
        batch_count = self.aggregation_config["volume_batch_count"]
        batch_size = self._get_adaptive_batch_size(chapter_num)
        volume_size = batch_count * batch_size

        return chapter_num % volume_size == 0

    def _calculate_batch_start(self, chapter_num: int, batch_size: int) -> int:
        """🔥 P4新增: 计算批次起始章节"""
        # 如果有单元边界,从边界后开始
        if self._arc_boundaries:
            last_arc = self._arc_boundaries[-1]
            if chapter_num - last_arc < batch_size * 2:
                return last_arc + 1

        return max(1, chapter_num - batch_size + 1)

    def _calculate_volume_start(self, chapter_num: int) -> int:
        """🔥 P4新增: 计算卷级聚合起始章节"""
        batch_count = self.aggregation_config["volume_batch_count"]
        batch_size = self._get_adaptive_batch_size(chapter_num)
        volume_size = batch_count * batch_size

        return max(1, chapter_num - volume_size + 1)

    def _trigger_arc_boundary_aggregation(self, chapter_num: int, arc_name: str = None):
        """
        🔥 P4新增: 单元边界聚合

        当一个叙事单元(Arc)结束时,生成该单元的综述
        """
        # 计算单元范围
        start = self._last_arc_chapter + 1 if self._last_arc_chapter > 0 else 1
        end = chapter_num

        if end <= start:
            return

        # 获取源摘要
        sources = []
        for i in range(start, end + 1):
            s = self.memory.get_chapter_summary(i)
            if s and s != "暂无摘要。":
                sources.append(f"[Ch{i}]: {s}")

        if not sources:
            print(f"   ⚠️ Arc聚合失败: 无可用摘要 ({start}-{end})")
            return

        try:
            arc_summary = self.batch_chain.invoke({
                "summaries": "\n".join(sources)
            })

            # 存储为 arc 级别
            level_name = f"arc_{arc_name}" if arc_name else "arc"
            self.memory.save_aggregated_summary(level_name, start, end, arc_summary)
            print(f"   ✅ [Summarizer] Arc聚合完成: {arc_name or 'Unknown'} (Ch{start}-{end}, {len(arc_summary)}字)")

        except Exception as e:
            print(f"   ❌ [Summarizer] Arc聚合出错: {e}")

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
        """
        🔥 P5升级: 生成摘要并提取高光时刻 (JSON Pipeline)
        """
        from core.json_repair import clean_json
        import json

        try:
            response = self.chain.invoke({"content": content})
            cleaned = clean_json(response)
            data = json.loads(cleaned)
            
            # 1. 存储摘要 (Dry Logic)
            summary_text = data.get("summary", "暂无摘要")
            self.memory.update_chapter_summary(chapter_num, summary_text)
            
            # 2. 存储高光 (Wet Emotion)
            highlights = data.get("highlights", [])
            for h in highlights:
                self.memory.save_highlight(
                    chapter_num=chapter_num,
                    content=h.get("content", ""),
                    tags=h.get("tags", []),
                    sentiment=h.get("sentiment", "Neutral")
                )
            
            print(f"   📝 Summary Generated (Ch{chapter_num}): {len(summary_text)} chars")
            print(f"   ✨ Highlights Saved: {len(highlights)} fragments")
            
            return summary_text
            
        except Exception as e:
            print(f"   ⚠️ Summary Generation Failed (Fallback to raw): {e}")
            # Fallback: Treat raw response as summary if JSON fails completely
            # But usually clean_json handles most cases.
            raw_summary = str(response)[:500]
            self.memory.update_chapter_summary(chapter_num, raw_summary)
            return raw_summary
