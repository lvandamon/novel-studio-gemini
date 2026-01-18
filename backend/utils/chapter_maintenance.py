"""
🔥 章节维护工具 (Chapter Maintenance Tool)

功能：
1. 每100章自动执行维护任务
2. 数据库完整性检查
3. 数据库优化（WAL checkpoint, VACUUM）
4. Neo4j图谱归档（归档旧事件）
5. 伏笔健康度检查
6. 自动备份
7. 性能统计报告
"""

import sqlite3
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
import sys

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.memory import MemoryManager
from utils.integrity_check import IntegrityChecker


class ChapterMaintenanceTool:
    """章节维护工具"""

    def __init__(self, db_path: str = "data/novel.db", backup_dir: str = "backups"):
        self.db_path = db_path
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.memory = MemoryManager(db_path=db_path)

    def should_run_maintenance(self, chapter_num: int) -> bool:
        """判断是否需要执行维护（每100章）"""
        return chapter_num > 0 and chapter_num % 100 == 0

    def run_maintenance(self, chapter_num: int, force: bool = False) -> Dict[str, Any]:
        """
        执行完整维护流程

        Args:
            chapter_num: 当前章节号
            force: 强制执行（忽略100章检查）

        Returns:
            维护报告
        """
        if not force and not self.should_run_maintenance(chapter_num):
            return {"status": "skipped", "reason": "Not at 100-chapter interval"}

        print(f"\n{'='*60}")
        print(f"🔧 开始第 {chapter_num} 章维护流程...")
        print(f"{'='*60}\n")

        report = {
            "chapter_num": chapter_num,
            "timestamp": datetime.now().isoformat(),
            "tasks": {}
        }

        # 1. 数据库完整性检查
        print("1️⃣ 数据库完整性检查...")
        integrity_result = self._check_integrity()
        report["tasks"]["integrity_check"] = integrity_result
        print(f"   {'✅' if integrity_result['status'] == 'HEALTHY' else '⚠️'} 完整性检查完成\n")

        # 2. 数据库优化
        print("2️⃣ 数据库优化（WAL checkpoint + VACUUM）...")
        optimization_result = self._optimize_database()
        report["tasks"]["database_optimization"] = optimization_result
        print(f"   ✅ 数据库优化完成\n")

        # 3. Neo4j图谱归档
        print("3️⃣ Neo4j图谱归档（归档500章前的旧事件）...")
        archive_result = self._archive_old_events(chapter_num)
        report["tasks"]["graph_archive"] = archive_result
        print(f"   ✅ 图谱归档完成\n")

        # 4. 伏笔健康度检查
        print("4️⃣ 伏笔健康度检查...")
        foreshadowing_result = self._check_foreshadowing_health(chapter_num)
        report["tasks"]["foreshadowing_health"] = foreshadowing_result
        print(f"   ✅ 伏笔健康度检查完成\n")

        # 5. 数据库备份
        print("5️⃣ 创建数据库备份...")
        backup_result = self._create_backup(chapter_num)
        report["tasks"]["backup"] = backup_result
        print(f"   ✅ 备份完成: {backup_result['backup_file']}\n")

        # 6. 性能统计
        print("6️⃣ 性能统计...")
        stats_result = self._generate_statistics(chapter_num)
        report["tasks"]["statistics"] = stats_result
        print(f"   ✅ 统计完成\n")

        print(f"{'='*60}")
        print(f"✅ 第 {chapter_num} 章维护流程完成！")
        print(f"{'='*60}\n")

        # 生成摘要
        self._print_summary(report)

        return report

    def _check_integrity(self) -> Dict[str, Any]:
        """执行完整性检查"""
        checker = IntegrityChecker(db_path=self.db_path)
        report = checker.check_all()

        return {
            "status": report["status"],
            "total_issues": report["total_count"],
            "by_severity": report["by_severity"]
        }

    def _optimize_database(self) -> Dict[str, Any]:
        """优化数据库性能"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # WAL checkpoint
        cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        checkpoint_result = cursor.fetchone()

        # VACUUM（压缩数据库）
        cursor.execute("VACUUM")

        # ANALYZE（更新统计信息）
        cursor.execute("ANALYZE")

        # 获取数据库大小
        cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
        db_size = cursor.fetchone()[0]

        conn.close()

        return {
            "wal_checkpoint": checkpoint_result,
            "database_size_mb": round(db_size / 1024 / 1024, 2),
            "vacuum_completed": True,
            "analyze_completed": True
        }

    def _archive_old_events(self, current_chapter: int) -> Dict[str, Any]:
        """归档旧事件（Neo4j）"""
        try:
            archive_threshold = max(1, current_chapter - 500)

            # 调用图谱管理器的归档方法
            if hasattr(self.memory.graph, 'optimize_graph'):
                self.memory.graph.optimize_graph(archive_before_chapter=archive_threshold)
                archived_count = "Unknown"  # 实际应从graph返回
            else:
                archived_count = 0

            return {
                "threshold_chapter": archive_threshold,
                "archived_events": archived_count,
                "status": "success"
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e)
            }

    def _check_foreshadowing_health(self, current_chapter: int) -> Dict[str, Any]:
        """检查伏笔健康度"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 活跃伏笔数
        cursor.execute("SELECT COUNT(*) FROM foreshadowing WHERE status = 'active'")
        active_count = cursor.fetchone()[0]

        # 高重要度活跃伏笔
        cursor.execute("""
            SELECT COUNT(*) FROM foreshadowing
            WHERE status = 'active' AND importance >= 8
        """)
        high_importance_count = cursor.fetchone()[0]

        # 过期伏笔（超过100章未解决的高重要度伏笔）
        cursor.execute("""
            SELECT id, content, chapter_created, importance
            FROM foreshadowing
            WHERE status = 'active'
              AND importance >= 7
              AND chapter_created < ?
            LIMIT 10
        """, (current_chapter - 100,))
        stale_hooks = cursor.fetchall()

        conn.close()

        return {
            "active_count": active_count,
            "high_importance_count": high_importance_count,
            "stale_hooks_count": len(stale_hooks),
            "stale_hooks_sample": [
                {"id": h[0], "content": h[1][:50], "chapter": h[2], "importance": h[3]}
                for h in stale_hooks[:3]
            ]
        }

    def _create_backup(self, chapter_num: int) -> Dict[str, Any]:
        """创建数据库备份"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"novel_ch{chapter_num}_{timestamp}.db"

        # 复制数据库文件
        shutil.copy2(self.db_path, backup_file)

        # 压缩旧备份（保留最近10个）
        backups = sorted(self.backup_dir.glob("novel_ch*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old_backup in backups[10:]:
            # 压缩或删除
            old_backup.unlink()

        return {
            "backup_file": str(backup_file),
            "backup_size_mb": round(backup_file.stat().st_size / 1024 / 1024, 2),
            "total_backups": len(list(self.backup_dir.glob("novel_ch*.db")))
        }

    def _generate_statistics(self, current_chapter: int) -> Dict[str, Any]:
        """生成性能统计"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 角色数
        cursor.execute("SELECT COUNT(*) FROM characters")
        char_count = cursor.fetchone()[0]

        # 事件数
        cursor.execute("SELECT COUNT(*) FROM events")
        event_count = cursor.fetchone()[0]

        # 变更日志数
        cursor.execute("SELECT COUNT(*) FROM inventory_change_log")
        inventory_changes = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM status_effect_log")
        status_changes = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM body_status_log")
        body_changes = cursor.fetchone()[0]

        # 伏笔统计
        cursor.execute("SELECT status, COUNT(*) FROM foreshadowing GROUP BY status")
        foreshadowing_stats = dict(cursor.fetchall())

        # 最近10章平均遥测分数
        cursor.execute("""
            SELECT AVG(tension_score), AVG(reader_boredom), AVG(reader_expectation)
            FROM chapter_metrics
            WHERE chapter_num > ?
        """, (current_chapter - 10,))
        avg_scores = cursor.fetchone()

        conn.close()

        return {
            "chapter_count": current_chapter,
            "character_count": char_count,
            "event_count": event_count,
            "change_logs": {
                "inventory": inventory_changes,
                "status_effects": status_changes,
                "body_status": body_changes,
                "total": inventory_changes + status_changes + body_changes
            },
            "foreshadowing": foreshadowing_stats,
            "recent_metrics": {
                "avg_tension": round(avg_scores[0], 1) if avg_scores[0] else 0,
                "avg_boredom": round(avg_scores[1], 1) if avg_scores[1] else 0,
                "avg_expectation": round(avg_scores[2], 1) if avg_scores[2] else 0
            }
        }

    def _print_summary(self, report: Dict[str, Any]):
        """打印维护摘要"""
        print("\n📊 维护摘要报告")
        print("=" * 60)

        # 完整性
        integrity = report["tasks"]["integrity_check"]
        if integrity["status"] == "HEALTHY":
            print("✅ 数据完整性: 健康")
        else:
            print(f"⚠️  数据完整性: 发现 {integrity['total_issues']} 个问题")
            print(f"   错误: {integrity['by_severity']['error']}, 警告: {integrity['by_severity']['warning']}")

        # 数据库优化
        db_opt = report["tasks"]["database_optimization"]
        print(f"✅ 数据库大小: {db_opt['database_size_mb']} MB")

        # 伏笔健康
        foreshadowing = report["tasks"]["foreshadowing_health"]
        print(f"✅ 活跃伏笔: {foreshadowing['active_count']} 个")
        if foreshadowing["stale_hooks_count"] > 0:
            print(f"⚠️  过期伏笔: {foreshadowing['stale_hooks_count']} 个（建议回收）")

        # 统计
        stats = report["tasks"]["statistics"]
        print(f"✅ 角色数: {stats['character_count']}")
        print(f"✅ 事件数: {stats['event_count']}")
        print(f"✅ 变更日志: {stats['change_logs']['total']} 条")

        # 最近质量
        metrics = stats["recent_metrics"]
        print(f"✅ 最近10章平均张力: {metrics['avg_tension']}")
        print(f"✅ 最近10章平均厌烦度: {metrics['avg_boredom']}")

        print("=" * 60)


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Novel Studio Gemini 章节维护工具")
    parser.add_argument("chapter_num", type=int, help="当前章节号")
    parser.add_argument("--db", default="data/novel.db", help="数据库路径")
    parser.add_argument("--backup-dir", default="backups", help="备份目录")
    parser.add_argument("--force", action="store_true", help="强制执行（忽略100章检查）")
    parser.add_argument("--json", action="store_true", help="输出JSON格式报告")

    args = parser.parse_args()

    tool = ChapterMaintenanceTool(db_path=args.db, backup_dir=args.backup_dir)
    report = tool.run_maintenance(args.chapter_num, force=args.force)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
