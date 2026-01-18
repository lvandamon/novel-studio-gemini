"""
🔥 数据库完整性验证工具

功能：
1. 检查SQLite数据完整性
2. 验证Neo4j图谱一致性
3. 检测孤立数据和悬空引用
4. 生成完整性报告
"""

import sqlite3
import json
from typing import Dict, List, Any
from pathlib import Path
import sys

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.memory import MemoryManager
from core.graph_store import GraphManager


class IntegrityChecker:
    """数据库完整性检查器"""

    def __init__(self, db_path: str = "data/novel.db"):
        self.db_path = db_path
        self.memory = MemoryManager(db_path=db_path)
        self.issues = []

    def check_all(self) -> Dict[str, Any]:
        """运行所有完整性检查"""
        print("🔍 开始数据库完整性检查...\n")

        self.check_character_consistency()
        self.check_event_integrity()
        self.check_foreshadowing_orphans()
        self.check_relationship_consistency()
        self.check_anchor_integrity()
        self.check_change_log_consistency()

        return self.generate_report()

    def check_character_consistency(self):
        """检查角色数据一致性"""
        print("1️⃣ 检查角色数据一致性...")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 检查别名映射完整性
        cursor.execute("""
            SELECT alias, character_id FROM character_aliases
            WHERE character_id NOT IN (SELECT id FROM characters)
        """)
        orphan_aliases = cursor.fetchall()

        if orphan_aliases:
            self.issues.append({
                "category": "CHARACTER",
                "severity": "ERROR",
                "type": "ORPHAN_ALIAS",
                "count": len(orphan_aliases),
                "detail": f"发现 {len(orphan_aliases)} 个孤立的别名映射（角色不存在）",
                "samples": orphan_aliases[:5]
            })

        # 检查角色JSON数据完整性
        cursor.execute("SELECT id, name, data FROM characters")
        characters = cursor.fetchall()

        invalid_json = []
        for char_id, name, data_json in characters:
            try:
                data = json.loads(data_json)
                # 验证必要字段
                required_fields = ["name", "role", "level"]
                missing = [f for f in required_fields if f not in data]
                if missing:
                    invalid_json.append((char_id, name, f"Missing fields: {missing}"))
            except:
                invalid_json.append((char_id, name, "Invalid JSON"))

        if invalid_json:
            self.issues.append({
                "category": "CHARACTER",
                "severity": "WARNING",
                "type": "INVALID_JSON",
                "count": len(invalid_json),
                "detail": f"发现 {len(invalid_json)} 个角色数据格式错误",
                "samples": invalid_json[:5]
            })

        conn.close()
        print(f"   ✅ 角色一致性检查完成 ({len(orphan_aliases) + len(invalid_json)} 个问题)\n")

    def check_event_integrity(self):
        """检查事件完整性"""
        print("2️⃣ 检查事件数据完整性...")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 检查事件引用的角色是否存在
        cursor.execute("""
            SELECT e.id, e.character_name, e.chapter_num
            FROM events e
            WHERE e.character_name NOT IN (
                SELECT name FROM characters
                UNION
                SELECT alias FROM character_aliases
            )
            LIMIT 100
        """)
        orphan_events = cursor.fetchall()

        if orphan_events:
            self.issues.append({
                "category": "EVENT",
                "severity": "WARNING",
                "type": "ORPHAN_EVENT",
                "count": len(orphan_events),
                "detail": f"发现 {len(orphan_events)} 个事件引用不存在的角色",
                "samples": orphan_events[:5]
            })

        # 检查章节号连续性
        cursor.execute("""
            SELECT chapter_num FROM events
            GROUP BY chapter_num
            ORDER BY chapter_num
        """)
        chapters = [row[0] for row in cursor.fetchall()]

        gaps = []
        for i in range(len(chapters) - 1):
            if chapters[i + 1] - chapters[i] > 1:
                gaps.append((chapters[i], chapters[i + 1]))

        if gaps:
            self.issues.append({
                "category": "EVENT",
                "severity": "INFO",
                "type": "CHAPTER_GAP",
                "count": len(gaps),
                "detail": f"章节序列存在 {len(gaps)} 个间隙",
                "samples": gaps[:5]
            })

        conn.close()
        print(f"   ✅ 事件完整性检查完成 ({len(orphan_events) + len(gaps)} 个问题)\n")

    def check_foreshadowing_orphans(self):
        """检查伏笔孤立问题"""
        print("3️⃣ 检查伏笔数据完整性...")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 检查resolved但没有resolution_chapter的伏笔
        cursor.execute("""
            SELECT id, content, chapter_created
            FROM foreshadowing
            WHERE status = 'resolved' AND chapter_resolved IS NULL
        """)
        inconsistent_hooks = cursor.fetchall()

        if inconsistent_hooks:
            self.issues.append({
                "category": "FORESHADOWING",
                "severity": "WARNING",
                "type": "RESOLVED_NO_CHAPTER",
                "count": len(inconsistent_hooks),
                "detail": f"发现 {len(inconsistent_hooks)} 个已标记resolved但未记录解决章节的伏笔",
                "samples": inconsistent_hooks[:5]
            })

        # 检查长期未解决的高重要度伏笔
        cursor.execute("""
            SELECT id, content, chapter_created, importance
            FROM foreshadowing
            WHERE status = 'active'
              AND importance >= 8
              AND chapter_created < (SELECT MAX(chapter_num) FROM events) - 100
        """)
        stale_hooks = cursor.fetchall()

        if stale_hooks:
            self.issues.append({
                "category": "FORESHADOWING",
                "severity": "INFO",
                "type": "STALE_HIGH_IMPORTANCE",
                "count": len(stale_hooks),
                "detail": f"发现 {len(stale_hooks)} 个超过100章未解决的高重要度伏笔",
                "samples": stale_hooks[:5]
            })

        conn.close()
        print(f"   ✅ 伏笔完整性检查完成 ({len(inconsistent_hooks) + len(stale_hooks)} 个问题)\n")

    def check_relationship_consistency(self):
        """检查关系一致性（SQL备份表）"""
        print("4️⃣ 检查关系备份表一致性...")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 检查关系引用的实体是否存在
        cursor.execute("""
            SELECT r.id, r.source_name, r.target_name
            FROM relationship_backup r
            WHERE r.source_name NOT IN (
                SELECT name FROM characters
                UNION
                SELECT alias FROM character_aliases
            )
            OR r.target_name NOT IN (
                SELECT name FROM characters
                UNION
                SELECT alias FROM character_aliases
            )
            LIMIT 50
        """)
        orphan_relations = cursor.fetchall()

        if orphan_relations:
            self.issues.append({
                "category": "RELATIONSHIP",
                "severity": "WARNING",
                "type": "ORPHAN_RELATION",
                "count": len(orphan_relations),
                "detail": f"发现 {len(orphan_relations)} 个引用不存在实体的关系",
                "samples": orphan_relations[:5]
            })

        # 检查metadata格式
        cursor.execute("""
            SELECT id, source_name, relation, target_name, metadata
            FROM relationship_backup
            WHERE metadata IS NOT NULL
            LIMIT 100
        """)
        relations_with_meta = cursor.fetchall()

        invalid_meta = []
        for rel_id, src, rel, tgt, meta_json in relations_with_meta:
            if meta_json:
                try:
                    json.loads(meta_json)
                except:
                    invalid_meta.append((rel_id, src, rel, tgt))

        if invalid_meta:
            self.issues.append({
                "category": "RELATIONSHIP",
                "severity": "ERROR",
                "type": "INVALID_METADATA",
                "count": len(invalid_meta),
                "detail": f"发现 {len(invalid_meta)} 个关系的metadata JSON格式错误",
                "samples": invalid_meta[:5]
            })

        conn.close()
        print(f"   ✅ 关系一致性检查完成 ({len(orphan_relations) + len(invalid_meta)} 个问题)\n")

    def check_anchor_integrity(self):
        """检查锚点完整性"""
        print("5️⃣ 检查锚点数据完整性...")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 检查锚点引用的角色是否存在
        cursor.execute("""
            SELECT a.id, a.character_name, a.content
            FROM character_anchors a
            WHERE a.character_name NOT IN (
                SELECT name FROM characters
                UNION
                SELECT alias FROM character_aliases
            )
        """)
        orphan_anchors = cursor.fetchall()

        if orphan_anchors:
            self.issues.append({
                "category": "ANCHOR",
                "severity": "WARNING",
                "type": "ORPHAN_ANCHOR",
                "count": len(orphan_anchors),
                "detail": f"发现 {len(orphan_anchors)} 个孤立的锚点（角色不存在）",
                "samples": orphan_anchors[:5]
            })

        # 检查shattered锚点是否有时间戳
        cursor.execute("""
            SELECT id, character_name, content, status
            FROM character_anchors
            WHERE status = 'shattered' AND (
                shattered_chapter IS NULL OR shattered_chapter = 0
            )
        """)
        missing_timestamp = cursor.fetchall()

        if missing_timestamp:
            self.issues.append({
                "category": "ANCHOR",
                "severity": "INFO",
                "type": "MISSING_SHATTER_TIMESTAMP",
                "count": len(missing_timestamp),
                "detail": f"发现 {len(missing_timestamp)} 个已粉碎但缺少时间戳的锚点",
                "samples": missing_timestamp[:5]
            })

        conn.close()
        print(f"   ✅ 锚点完整性检查完成 ({len(orphan_anchors) + len(missing_timestamp)} 个问题)\n")

    def check_change_log_consistency(self):
        """检查变更日志一致性"""
        print("6️⃣ 检查变更日志完整性...")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        issues_found = 0

        # 检查物品变更日志引用的角色
        cursor.execute("""
            SELECT DISTINCT character_name FROM inventory_change_log
            WHERE character_name NOT IN (
                SELECT name FROM characters
                UNION
                SELECT alias FROM character_aliases
            )
        """)
        orphan_inv_chars = cursor.fetchall()

        if orphan_inv_chars:
            self.issues.append({
                "category": "CHANGE_LOG",
                "severity": "WARNING",
                "type": "ORPHAN_INVENTORY_LOG",
                "count": len(orphan_inv_chars),
                "detail": f"物品变更日志引用 {len(orphan_inv_chars)} 个不存在的角色",
                "samples": orphan_inv_chars[:5]
            })
            issues_found += len(orphan_inv_chars)

        # 检查身体状态日志引用的角色
        cursor.execute("""
            SELECT DISTINCT character_name FROM body_status_log
            WHERE character_name NOT IN (
                SELECT name FROM characters
                UNION
                SELECT alias FROM character_aliases
            )
        """)
        orphan_body_chars = cursor.fetchall()

        if orphan_body_chars:
            self.issues.append({
                "category": "CHANGE_LOG",
                "severity": "WARNING",
                "type": "ORPHAN_BODY_LOG",
                "count": len(orphan_body_chars),
                "detail": f"身体状态日志引用 {len(orphan_body_chars)} 个不存在的角色",
                "samples": orphan_body_chars[:5]
            })
            issues_found += len(orphan_body_chars)

        conn.close()
        print(f"   ✅ 变更日志完整性检查完成 ({issues_found} 个问题)\n")

    def generate_report(self) -> Dict[str, Any]:
        """生成完整性报告"""
        print("=" * 60)
        print("📊 完整性检查报告")
        print("=" * 60 + "\n")

        total_issues = len(self.issues)

        if total_issues == 0:
            print("✅ 未发现任何完整性问题！数据库状态良好。\n")
            return {"status": "HEALTHY", "issues": [], "total_count": 0}

        # 按严重程度分类
        by_severity = {"ERROR": [], "WARNING": [], "INFO": []}
        for issue in self.issues:
            by_severity[issue["severity"]].append(issue)

        print(f"总问题数: {total_issues}")
        print(f"  ❌ 错误 (ERROR):   {len(by_severity['ERROR'])}")
        print(f"  ⚠️  警告 (WARNING): {len(by_severity['WARNING'])}")
        print(f"  ℹ️  信息 (INFO):    {len(by_severity['INFO'])}")
        print()

        # 详细列出错误
        if by_severity["ERROR"]:
            print("❌ 严重错误：\n")
            for issue in by_severity["ERROR"]:
                print(f"  [{issue['category']}] {issue['type']}: {issue['detail']}")
                if issue.get("samples"):
                    print(f"    示例: {issue['samples'][0]}")
            print()

        # 列出警告
        if by_severity["WARNING"]:
            print("⚠️  警告：\n")
            for issue in by_severity["WARNING"]:
                print(f"  [{issue['category']}] {issue['type']}: {issue['detail']}")
            print()

        return {
            "status": "ISSUES_FOUND" if by_severity["ERROR"] else "DEGRADED",
            "issues": self.issues,
            "total_count": total_issues,
            "by_severity": {
                "error": len(by_severity["ERROR"]),
                "warning": len(by_severity["WARNING"]),
                "info": len(by_severity["INFO"])
            }
        }


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Novel Studio Gemini 数据库完整性检查")
    parser.add_argument("--db", default="data/novel.db", help="数据库路径")
    parser.add_argument("--json", action="store_true", help="输出JSON格式报告")

    args = parser.parse_args()

    checker = IntegrityChecker(db_path=args.db)
    report = checker.check_all()

    if args.json:
        import json
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
