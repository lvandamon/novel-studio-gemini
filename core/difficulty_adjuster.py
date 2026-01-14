"""
🔥 P4新增: 动态难度调整器 (Dynamic Difficulty Adjuster)

功能:
1. 根据失败率自动调整Agent严格度
2. 根据成本自动调整预算分配
3. 根据质量指标自动调优参数
4. 提供自适应建议

使用场景:
- 工作流中自动调用
- Director决策时参考
- 系统自愈机制
"""

import sqlite3
import json
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class AgentPerformance:
    """Agent性能统计"""
    agent_name: str
    total_calls: int = 0
    failures: int = 0
    avg_latency: float = 0.0
    retry_count: int = 0
    last_updated: float = field(default_factory=time.time)

    @property
    def failure_rate(self) -> float:
        return self.failures / max(1, self.total_calls)


class DifficultyAdjuster:
    """
    动态难度调整器

    自动根据系统运行状态调整各Agent的参数,
    保证在保持质量的前提下最大化效率。
    """

    # 默认Agent参数
    DEFAULT_PARAMS = {
        "Simulator": {
            "max_retries": 3,
            "strictness": 0.7,  # 0-1, 1=最严格
            "timeout_ms": 30000
        },
        "Reviewer": {
            "logic_threshold": 80,
            "ooc_tolerance": 0.1,
            "force_block_threshold": 60
        },
        "Writer": {
            "max_revisions": 3,
            "self_critique_depth": 2,
            "anchor_check_strictness": 0.8
        },
        "Foreshadowing": {
            "core_hook_threshold": 0.85,
            "subplot_threshold": 0.75,
            "require_entity_match": True
        }
    }

    # 调整策略
    ADJUSTMENT_RULES = {
        "high_failure": {
            "threshold": 0.4,  # 失败率 > 40%
            "action": "relax",
            "params": {
                "Simulator.strictness": -0.1,
                "Reviewer.logic_threshold": -5,
                "Writer.max_revisions": +1
            }
        },
        "low_failure": {
            "threshold": 0.1,  # 失败率 < 10%
            "action": "tighten",
            "params": {
                "Simulator.strictness": +0.05,
                "Reviewer.logic_threshold": +2
            }
        },
        "high_cost": {
            "threshold": 0.8,  # 成本使用率 > 80%
            "action": "optimize",
            "params": {
                "Writer.self_critique_depth": -1,
                "Writer.max_revisions": -1
            }
        }
    }

    def __init__(self, db_path: str = "data/novel.db"):
        self.db_path = db_path
        self._current_params = self._deep_copy_params(self.DEFAULT_PARAMS)
        self._performance_history: Dict[str, List[AgentPerformance]] = defaultdict(list)
        self._adjustment_log: List[Dict] = []
        self._init_db()

    def _deep_copy_params(self, params: Dict) -> Dict:
        """深拷贝参数"""
        import copy
        return copy.deepcopy(params)

    def _init_db(self):
        """初始化难度调整表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS difficulty_params (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_num INTEGER,
                params_json TEXT,
                adjustment_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_performance_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_num INTEGER,
                agent_name TEXT,
                success BOOLEAN,
                latency_ms INTEGER,
                retry_count INTEGER,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()

    def record_agent_result(self, agent_name: str, chapter_num: int,
                            success: bool, latency_ms: int = 0,
                            retry_count: int = 0, notes: str = ""):
        """
        记录Agent执行结果

        Args:
            agent_name: Agent名称
            chapter_num: 章节号
            success: 是否成功
            latency_ms: 耗时(毫秒)
            retry_count: 重试次数
            notes: 备注
        """
        # 更新内存统计
        perf = self._get_or_create_performance(agent_name)
        perf.total_calls += 1
        if not success:
            perf.failures += 1
        perf.retry_count += retry_count
        perf.avg_latency = (perf.avg_latency * (perf.total_calls - 1) + latency_ms) / perf.total_calls
        perf.last_updated = time.time()

        # 持久化
        self._save_performance_log(chapter_num, agent_name, success, latency_ms, retry_count, notes)

        # 检查是否需要调整
        self._check_and_adjust(agent_name, chapter_num)

    def _get_or_create_performance(self, agent_name: str) -> AgentPerformance:
        """获取或创建Agent性能记录"""
        history = self._performance_history[agent_name]
        if not history or time.time() - history[-1].last_updated > 3600:  # 每小时新建
            perf = AgentPerformance(agent_name=agent_name)
            history.append(perf)
        return history[-1]

    def _save_performance_log(self, chapter_num: int, agent_name: str,
                              success: bool, latency_ms: int,
                              retry_count: int, notes: str):
        """保存性能日志"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO agent_performance_log
            (chapter_num, agent_name, success, latency_ms, retry_count, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (chapter_num, agent_name, success, latency_ms, retry_count, notes))

        conn.commit()
        conn.close()

    def _check_and_adjust(self, agent_name: str, chapter_num: int):
        """检查是否需要调整参数"""
        perf = self._get_or_create_performance(agent_name)

        # 至少5次调用后再做判断
        if perf.total_calls < 5:
            return

        failure_rate = perf.failure_rate

        # 高失败率 -> 放松限制
        if failure_rate > self.ADJUSTMENT_RULES["high_failure"]["threshold"]:
            self._apply_adjustment("high_failure", agent_name, chapter_num, failure_rate)

        # 低失败率 -> 收紧限制 (可选)
        elif failure_rate < self.ADJUSTMENT_RULES["low_failure"]["threshold"] and perf.total_calls >= 10:
            self._apply_adjustment("low_failure", agent_name, chapter_num, failure_rate)

    def _apply_adjustment(self, rule_name: str, agent_name: str,
                          chapter_num: int, trigger_value: float):
        """应用参数调整"""
        rule = self.ADJUSTMENT_RULES[rule_name]

        # 检查是否最近已调整过 (避免频繁调整)
        if self._adjustment_log:
            last_adj = self._adjustment_log[-1]
            if last_adj.get("agent") == agent_name and \
               time.time() - last_adj.get("timestamp", 0) < 300:  # 5分钟内不重复调整
                return

        adjustments_made = []

        for param_path, delta in rule["params"].items():
            parts = param_path.split(".")
            if len(parts) != 2:
                continue

            target_agent, param_name = parts

            # 只调整相关Agent或通用参数
            if target_agent != agent_name and target_agent not in ["Writer", "Reviewer"]:
                continue

            # 应用调整
            if target_agent in self._current_params:
                old_value = self._current_params[target_agent].get(param_name)
                if old_value is not None:
                    new_value = old_value + delta

                    # 边界保护
                    if "strictness" in param_name or "threshold" in param_name.lower():
                        new_value = max(0.3, min(1.0, new_value)) if "strictness" in param_name else max(50, min(95, new_value))

                    self._current_params[target_agent][param_name] = new_value
                    adjustments_made.append(f"{param_path}: {old_value} -> {new_value}")

        if adjustments_made:
            log_entry = {
                "agent": agent_name,
                "rule": rule_name,
                "trigger_value": trigger_value,
                "adjustments": adjustments_made,
                "timestamp": time.time(),
                "chapter": chapter_num
            }
            self._adjustment_log.append(log_entry)
            self._save_adjustment(chapter_num, log_entry)

            print(f"   🔧 难度自动调整 [{rule_name}]: {', '.join(adjustments_made)}")

    def _save_adjustment(self, chapter_num: int, log_entry: Dict):
        """保存调整记录"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO difficulty_params
            (chapter_num, params_json, adjustment_reason)
            VALUES (?, ?, ?)
        ''', (
            chapter_num,
            json.dumps(self._current_params, ensure_ascii=False),
            json.dumps(log_entry, ensure_ascii=False)
        ))

        conn.commit()
        conn.close()

    def get_param(self, agent_name: str, param_name: str, default: Any = None) -> Any:
        """获取Agent参数"""
        return self._current_params.get(agent_name, {}).get(param_name, default)

    def get_all_params(self, agent_name: str = None) -> Dict:
        """获取所有参数"""
        if agent_name:
            return self._current_params.get(agent_name, {})
        return self._current_params

    def suggest_optimization(self, chapter_num: int) -> Dict[str, Any]:
        """
        生成优化建议

        基于最近的性能数据,给出系统调优建议
        """
        suggestions = {
            "chapter": chapter_num,
            "agent_suggestions": [],
            "system_suggestions": [],
            "priority": "NORMAL"
        }

        # 分析各Agent
        for agent_name, history in self._performance_history.items():
            if not history:
                continue

            recent_perf = history[-1]

            if recent_perf.failure_rate > 0.5:
                suggestions["agent_suggestions"].append({
                    "agent": agent_name,
                    "issue": "失败率过高",
                    "rate": f"{recent_perf.failure_rate:.1%}",
                    "suggestion": f"建议降低{agent_name}的严格度参数"
                })
                suggestions["priority"] = "HIGH"

            elif recent_perf.avg_latency > 60000:  # 60秒
                suggestions["agent_suggestions"].append({
                    "agent": agent_name,
                    "issue": "响应过慢",
                    "latency": f"{recent_perf.avg_latency/1000:.1f}s",
                    "suggestion": "建议简化该Agent的任务复杂度"
                })

        # 系统级建议
        total_failures = sum(h[-1].failures for h in self._performance_history.values() if h)
        total_calls = sum(h[-1].total_calls for h in self._performance_history.values() if h)

        if total_calls > 0:
            system_failure_rate = total_failures / total_calls
            if system_failure_rate > 0.3:
                suggestions["system_suggestions"].append(
                    "系统整体失败率偏高,建议检查LLM连接稳定性或降低整体严格度"
                )
                suggestions["priority"] = "HIGH"

        if len(self._adjustment_log) > 5:
            recent_adjustments = [a for a in self._adjustment_log if time.time() - a["timestamp"] < 3600]
            if len(recent_adjustments) > 3:
                suggestions["system_suggestions"].append(
                    "参数频繁调整,建议人工检查系统配置是否合理"
                )

        return suggestions

    def reset_to_defaults(self):
        """重置为默认参数"""
        self._current_params = self._deep_copy_params(self.DEFAULT_PARAMS)
        self._adjustment_log.append({
            "rule": "MANUAL_RESET",
            "timestamp": time.time(),
            "adjustments": ["恢复默认参数"]
        })
        print("   🔄 难度参数已重置为默认值")

    def generate_report(self) -> str:
        """生成难度调整报告"""
        lines = ["=" * 50, "🔧 难度调整报告", "=" * 50]

        # Agent性能概览
        lines.append("\n【Agent性能】")
        for agent_name, history in self._performance_history.items():
            if not history:
                continue
            perf = history[-1]
            status = "🟢" if perf.failure_rate < 0.2 else ("🟡" if perf.failure_rate < 0.4 else "🔴")
            lines.append(f"  {status} {agent_name}: {perf.total_calls}次, 失败{perf.failures}次 ({perf.failure_rate:.1%})")

        # 当前参数
        lines.append("\n【当前参数】")
        for agent, params in self._current_params.items():
            lines.append(f"  {agent}:")
            for k, v in params.items():
                lines.append(f"    {k}: {v}")

        # 最近调整
        if self._adjustment_log:
            lines.append("\n【最近调整】")
            for adj in self._adjustment_log[-5:]:
                lines.append(f"  - [{adj.get('rule')}] {', '.join(adj.get('adjustments', []))}")

        return "\n".join(lines)


# 全局单例
_adjuster_instance: Optional[DifficultyAdjuster] = None


def get_difficulty_adjuster(db_path: str = "data/novel.db") -> DifficultyAdjuster:
    """获取全局难度调整器实例"""
    global _adjuster_instance
    if _adjuster_instance is None:
        _adjuster_instance = DifficultyAdjuster(db_path)
    return _adjuster_instance
