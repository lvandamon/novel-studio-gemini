"""
🔥 P4新增: LLM成本监控模块 (Cost Monitor)

功能:
1. 跟踪每章节/每Agent的Token消耗
2. 成本累计与预警
3. 失败率监控
4. 自动降级建议

成本计算基于 DeepSeek 官方定价 (2024):
- DeepSeek-V3 (Chat): ¥1/M input, ¥2/M output (缓存命中 ¥0.1/M)
- DeepSeek-R1 (Reasoner): ¥4/M input, ¥16/M output (缓存命中 ¥0.5/M)
"""

import time
import json
import sqlite3
import threading
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime


@dataclass
class TokenUsage:
    """单次调用的Token使用记录"""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    model: str = ""
    agent: str = ""
    chapter: int = 0
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    latency_ms: int = 0


class CostMonitor:
    """
    LLM成本监控器

    功能:
    1. 实时Token统计
    2. 成本预警
    3. 失败率监控
    4. 章节级报告
    """

    # 定价表 (每百万Token, 人民币)
    PRICING = {
        "deepseek-chat": {
            "input": 1.0,
            "output": 2.0,
            "cached": 0.1
        },
        "deepseek-reasoner": {
            "input": 4.0,
            "output": 16.0,
            "cached": 0.5
        }
    }

    # 预警阈值
    DEFAULT_CHAPTER_BUDGET = 5.0  # 每章默认预算 (元)
    DEFAULT_SESSION_BUDGET = 100.0  # 每次会话默认预算 (元)

    def __init__(self, db_path: str = "data/novel.db"):
        self.db_path = db_path
        self._lock = threading.Lock()

        # 内存统计
        self._session_usage: List[TokenUsage] = []
        self._chapter_usage: Dict[int, List[TokenUsage]] = defaultdict(list)
        self._agent_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {
            "calls": 0, "failures": 0, "total_input": 0, "total_output": 0
        })

        # 预算设置
        self.chapter_budget = self.DEFAULT_CHAPTER_BUDGET
        self.session_budget = self.DEFAULT_SESSION_BUDGET

        # 预警状态
        self._warnings: List[Dict[str, Any]] = []

        # 初始化数据库表
        self._init_db()

    def _init_db(self):
        """初始化成本监控表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 成本日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cost_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_num INTEGER,
                agent_name TEXT,
                model TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                cached_tokens INTEGER,
                cost_yuan REAL,
                success BOOLEAN,
                latency_ms INTEGER,
                timestamp REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 章节成本汇总表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chapter_cost_summary (
                chapter_num INTEGER PRIMARY KEY,
                total_input_tokens INTEGER DEFAULT 0,
                total_output_tokens INTEGER DEFAULT 0,
                total_cost_yuan REAL DEFAULT 0,
                call_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                avg_latency_ms INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cost_chapter ON cost_log(chapter_num)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cost_agent ON cost_log(agent_name)')

        conn.commit()
        conn.close()

    def record_usage(self, usage: TokenUsage):
        """
        记录一次Token使用

        Args:
            usage: TokenUsage对象
        """
        with self._lock:
            # 内存统计
            self._session_usage.append(usage)
            self._chapter_usage[usage.chapter].append(usage)

            # Agent统计
            agent_stat = self._agent_stats[usage.agent]
            agent_stat["calls"] += 1
            agent_stat["total_input"] += usage.input_tokens
            agent_stat["total_output"] += usage.output_tokens
            if not usage.success:
                agent_stat["failures"] += 1

            # 计算成本
            cost = self._calculate_cost(usage)

            # 持久化到数据库
            self._persist_usage(usage, cost)

            # 检查预警
            self._check_warnings(usage.chapter)

    def _calculate_cost(self, usage: TokenUsage) -> float:
        """计算单次调用成本 (元)"""
        pricing = self.PRICING.get(usage.model, self.PRICING["deepseek-chat"])

        # 转换为百万Token
        input_m = usage.input_tokens / 1_000_000
        output_m = usage.output_tokens / 1_000_000
        cached_m = usage.cached_tokens / 1_000_000

        cost = (
            (input_m - cached_m) * pricing["input"] +
            output_m * pricing["output"] +
            cached_m * pricing["cached"]
        )
        return round(cost, 4)

    def _persist_usage(self, usage: TokenUsage, cost: float):
        """持久化到数据库"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            cursor = conn.cursor()

            # 插入日志
            cursor.execute('''
                INSERT INTO cost_log
                (chapter_num, agent_name, model, input_tokens, output_tokens,
                 cached_tokens, cost_yuan, success, latency_ms, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                usage.chapter, usage.agent, usage.model,
                usage.input_tokens, usage.output_tokens, usage.cached_tokens,
                cost, usage.success, usage.latency_ms, usage.timestamp
            ))

            # 更新章节汇总
            cursor.execute('''
                INSERT INTO chapter_cost_summary
                (chapter_num, total_input_tokens, total_output_tokens, total_cost_yuan,
                 call_count, failure_count, avg_latency_ms)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(chapter_num) DO UPDATE SET
                    total_input_tokens = total_input_tokens + excluded.total_input_tokens,
                    total_output_tokens = total_output_tokens + excluded.total_output_tokens,
                    total_cost_yuan = total_cost_yuan + excluded.total_cost_yuan,
                    call_count = call_count + 1,
                    failure_count = failure_count + excluded.failure_count,
                    avg_latency_ms = (avg_latency_ms * call_count + excluded.avg_latency_ms) / (call_count + 1),
                    updated_at = CURRENT_TIMESTAMP
            ''', (
                usage.chapter, usage.input_tokens, usage.output_tokens, cost,
                0 if usage.success else 1, usage.latency_ms
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"   ⚠️ 成本日志持久化失败: {e}")

    def _check_warnings(self, chapter_num: int):
        """检查是否触发预警"""
        # 章节预算检查
        chapter_cost = self.get_chapter_cost(chapter_num)
        if chapter_cost > self.chapter_budget:
            warning = {
                "type": "CHAPTER_BUDGET_EXCEEDED",
                "chapter": chapter_num,
                "cost": chapter_cost,
                "budget": self.chapter_budget,
                "timestamp": time.time(),
                "message": f"章节{chapter_num}成本({chapter_cost:.2f}元)超出预算({self.chapter_budget}元)"
            }
            self._warnings.append(warning)
            print(f"   ⚠️ 成本预警: {warning['message']}")

        # 会话预算检查
        session_cost = self.get_session_cost()
        if session_cost > self.session_budget:
            warning = {
                "type": "SESSION_BUDGET_EXCEEDED",
                "cost": session_cost,
                "budget": self.session_budget,
                "timestamp": time.time(),
                "message": f"会话总成本({session_cost:.2f}元)超出预算({self.session_budget}元)"
            }
            if not any(w["type"] == "SESSION_BUDGET_EXCEEDED" for w in self._warnings):
                self._warnings.append(warning)
                print(f"   🚨 严重预警: {warning['message']}")

        # 失败率检查
        for agent, stats in self._agent_stats.items():
            if stats["calls"] >= 5:
                failure_rate = stats["failures"] / stats["calls"]
                if failure_rate > 0.3:  # 30%失败率
                    warning = {
                        "type": "HIGH_FAILURE_RATE",
                        "agent": agent,
                        "failure_rate": failure_rate,
                        "timestamp": time.time(),
                        "message": f"Agent [{agent}] 失败率过高: {failure_rate:.1%}"
                    }
                    if not any(w.get("agent") == agent and w["type"] == "HIGH_FAILURE_RATE"
                               for w in self._warnings[-10:]):
                        self._warnings.append(warning)
                        print(f"   ⚠️ {warning['message']}")

    def get_chapter_cost(self, chapter_num: int) -> float:
        """获取指定章节的总成本"""
        total = 0.0
        for usage in self._chapter_usage.get(chapter_num, []):
            total += self._calculate_cost(usage)
        return total

    def get_session_cost(self) -> float:
        """获取当前会话的总成本"""
        total = 0.0
        for usage in self._session_usage:
            total += self._calculate_cost(usage)
        return total

    def get_agent_stats(self, agent_name: str = None) -> Dict[str, Any]:
        """获取Agent统计信息"""
        if agent_name:
            stats = self._agent_stats.get(agent_name, {})
            if stats:
                stats["failure_rate"] = stats["failures"] / max(1, stats["calls"])
                stats["avg_input"] = stats["total_input"] / max(1, stats["calls"])
                stats["avg_output"] = stats["total_output"] / max(1, stats["calls"])
            return stats

        # 返回所有Agent统计
        result = {}
        for agent, stats in self._agent_stats.items():
            result[agent] = {
                **stats,
                "failure_rate": stats["failures"] / max(1, stats["calls"]),
                "avg_input": stats["total_input"] / max(1, stats["calls"]),
                "avg_output": stats["total_output"] / max(1, stats["calls"])
            }
        return result

    def get_warnings(self, clear: bool = False) -> List[Dict[str, Any]]:
        """获取所有预警"""
        warnings = self._warnings.copy()
        if clear:
            self._warnings.clear()
        return warnings

    def generate_report(self, chapter_num: int = None) -> str:
        """生成成本报告"""
        lines = ["=" * 50, "📊 LLM成本监控报告", "=" * 50]

        # 会话总览
        session_cost = self.get_session_cost()
        total_calls = len(self._session_usage)
        total_failures = sum(1 for u in self._session_usage if not u.success)

        lines.append(f"\n【会话总览】")
        lines.append(f"  总成本: ¥{session_cost:.2f}")
        lines.append(f"  总调用: {total_calls} 次")
        lines.append(f"  失败数: {total_failures} 次 ({total_failures/max(1,total_calls):.1%})")

        # 章节明细
        if chapter_num:
            chapter_cost = self.get_chapter_cost(chapter_num)
            chapter_calls = len(self._chapter_usage.get(chapter_num, []))
            lines.append(f"\n【第{chapter_num}章明细】")
            lines.append(f"  成本: ¥{chapter_cost:.2f}")
            lines.append(f"  调用: {chapter_calls} 次")

        # Agent统计
        lines.append(f"\n【Agent统计】")
        for agent, stats in sorted(self._agent_stats.items()):
            failure_rate = stats["failures"] / max(1, stats["calls"])
            status = "🔴" if failure_rate > 0.3 else ("🟡" if failure_rate > 0.1 else "🟢")
            lines.append(f"  {status} {agent}: {stats['calls']}次, 失败{stats['failures']}次 ({failure_rate:.1%})")

        # 预警
        if self._warnings:
            lines.append(f"\n【预警记录】")
            for w in self._warnings[-5:]:
                lines.append(f"  ⚠️ {w['message']}")

        lines.append("=" * 50)
        return "\n".join(lines)

    def get_cost_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取历史成本记录 (用于图表展示)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT chapter_num, total_cost_yuan, call_count, failure_count
                FROM chapter_cost_summary
                ORDER BY chapter_num DESC
                LIMIT ?
            ''', (limit,))
            rows = cursor.fetchall()
            conn.close()

            return [
                {
                    "chapter": r[0],
                    "cost": r[1],
                    "calls": r[2],
                    "failures": r[3]
                }
                for r in reversed(rows)
            ]
        except Exception as e:
            print(f"   ⚠️ 获取成本历史失败: {e}")
            return []

    def should_suggest_degradation(self) -> Optional[Dict[str, Any]]:
        """
        检查是否应该建议降级

        Returns:
            如果需要降级,返回建议信息; 否则返回None
        """
        # 检查高失败率Agent
        for agent, stats in self._agent_stats.items():
            if stats["calls"] >= 3 and stats["failures"] / stats["calls"] > 0.5:
                return {
                    "type": "AGENT_DEGRADATION",
                    "agent": agent,
                    "reason": f"失败率过高 ({stats['failures']}/{stats['calls']})",
                    "suggestion": "建议简化该Agent的任务复杂度或增加重试次数"
                }

        # 检查成本爆炸
        session_cost = self.get_session_cost()
        if session_cost > self.session_budget * 0.8:
            return {
                "type": "COST_DEGRADATION",
                "cost": session_cost,
                "budget": self.session_budget,
                "reason": "成本接近预算上限",
                "suggestion": "建议减少检索深度、压缩上下文或暂停非核心Agent"
            }

        return None

    def set_budgets(self, chapter_budget: float = None, session_budget: float = None):
        """设置预算阈值"""
        if chapter_budget is not None:
            self.chapter_budget = chapter_budget
        if session_budget is not None:
            self.session_budget = session_budget


# 全局单例
_monitor_instance: Optional[CostMonitor] = None


def get_cost_monitor(db_path: str = "data/novel.db") -> CostMonitor:
    """获取全局成本监控器实例"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = CostMonitor(db_path)
    return _monitor_instance


def track_llm_call(agent: str, model: str, chapter: int = 0):
    """
    装饰器: 跟踪LLM调用

    Usage:
        @track_llm_call("Writer", "deepseek-chat", chapter_num)
        def some_llm_operation():
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            monitor = get_cost_monitor()
            start_time = time.time()
            success = True
            input_tokens = 0
            output_tokens = 0

            try:
                result = func(*args, **kwargs)

                # 尝试从结果中提取Token信息
                # (需要根据实际LLM返回格式调整)
                if hasattr(result, 'usage_metadata'):
                    usage = result.usage_metadata
                    input_tokens = usage.get('input_tokens', 0)
                    output_tokens = usage.get('output_tokens', 0)

                return result
            except Exception as e:
                success = False
                raise
            finally:
                latency = int((time.time() - start_time) * 1000)
                usage = TokenUsage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model=model,
                    agent=agent,
                    chapter=chapter,
                    success=success,
                    latency_ms=latency
                )
                monitor.record_usage(usage)

        return wrapper
    return decorator
