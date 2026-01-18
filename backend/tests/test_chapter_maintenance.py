"""
🔥 章节维护工具测试

测试内容:
1. 100章检查触发条件
2. 数据库优化执行
3. 备份创建
4. 统计数据生成
"""

import sys
from pathlib import Path
import sqlite3
import tempfile
import shutil

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.chapter_maintenance import ChapterMaintenanceTool


def setup_test_database(db_path: str):
    """创建测试数据库"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 创建基础表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS characters (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            data TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter_num INTEGER,
            character_name TEXT,
            description TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS foreshadowing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT,
            status TEXT DEFAULT 'active',
            importance INTEGER DEFAULT 5,
            chapter_created INTEGER,
            chapter_resolved INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory_change_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_name TEXT,
            item_name TEXT,
            chapter_num INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS status_effect_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_name TEXT,
            chapter_num INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS body_status_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_name TEXT,
            chapter_num INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chapter_metrics (
            chapter_num INTEGER PRIMARY KEY,
            tension_score REAL,
            reader_boredom REAL,
            reader_expectation REAL
        )
    """)

    # 插入测试数据
    cursor.execute("INSERT INTO characters (id, name, data) VALUES ('1', '韩立', '{}')")
    cursor.execute("INSERT INTO events (chapter_num, character_name, description) VALUES (1, '韩立', '测试事件')")
    cursor.execute("INSERT INTO foreshadowing (content, chapter_created, importance) VALUES ('测试伏笔', 1, 8)")
    cursor.execute("INSERT INTO chapter_metrics (chapter_num, tension_score, reader_boredom, reader_expectation) VALUES (95, 75.0, 30.0, 80.0)")

    conn.commit()
    conn.close()


def test_should_run_maintenance():
    """测试维护触发条件"""
    print("\n=== 测试维护触发条件 ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        setup_test_database(str(db_path))

        tool = ChapterMaintenanceTool(db_path=str(db_path))

        # 测试不同章节号
        assert tool.should_run_maintenance(50) is False
        print("✓ 第50章: 不触发")

        assert tool.should_run_maintenance(100) is True
        print("✓ 第100章: 触发")

        assert tool.should_run_maintenance(200) is True
        print("✓ 第200章: 触发")

        assert tool.should_run_maintenance(199) is False
        print("✓ 第199章: 不触发")

    print("✅ 维护触发条件测试通过\n")


def test_run_maintenance():
    """测试完整维护流程"""
    print("\n=== 测试完整维护流程 ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        backup_dir = Path(tmpdir) / "backups"

        setup_test_database(str(db_path))

        tool = ChapterMaintenanceTool(db_path=str(db_path), backup_dir=str(backup_dir))

        # 执行维护
        report = tool.run_maintenance(100, force=True)

        # 验证报告结构
        assert "chapter_num" in report
        assert report["chapter_num"] == 100
        assert "tasks" in report
        assert "integrity_check" in report["tasks"]
        assert "database_optimization" in report["tasks"]
        assert "backup" in report["tasks"]
        assert "statistics" in report["tasks"]

        print(f"✓ 章节号: {report['chapter_num']}")
        print(f"✓ 任务数: {len(report['tasks'])}")

        # 验证完整性检查
        integrity = report["tasks"]["integrity_check"]
        assert "status" in integrity
        print(f"✓ 完整性检查: {integrity['status']}")

        # 验证数据库优化
        db_opt = report["tasks"]["database_optimization"]
        assert "database_size_mb" in db_opt
        assert db_opt["vacuum_completed"] is True
        print(f"✓ 数据库优化: {db_opt['database_size_mb']} MB")

        # 验证备份
        backup = report["tasks"]["backup"]
        assert "backup_file" in backup
        backup_file = Path(backup["backup_file"])
        assert backup_file.exists()
        print(f"✓ 备份创建: {backup_file.name}")

        # 验证统计
        stats = report["tasks"]["statistics"]
        assert "character_count" in stats
        assert stats["character_count"] == 1
        assert stats["event_count"] == 1
        print(f"✓ 统计数据: {stats['character_count']} 个角色, {stats['event_count']} 个事件")

    print("✅ 完整维护流程测试通过\n")


def test_database_optimization():
    """测试数据库优化"""
    print("\n=== 测试数据库优化 ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        setup_test_database(str(db_path))

        tool = ChapterMaintenanceTool(db_path=str(db_path))

        result = tool._optimize_database()

        assert "database_size_mb" in result
        assert "vacuum_completed" in result
        assert "analyze_completed" in result
        assert result["vacuum_completed"] is True
        assert result["analyze_completed"] is True

        print(f"✓ 数据库大小: {result['database_size_mb']} MB")
        print(f"✓ VACUUM 完成: {result['vacuum_completed']}")
        print(f"✓ ANALYZE 完成: {result['analyze_completed']}")

    print("✅ 数据库优化测试通过\n")


def test_foreshadowing_health():
    """测试伏笔健康度检查"""
    print("\n=== 测试伏笔健康度检查 ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        setup_test_database(str(db_path))

        # 添加更多测试数据
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("INSERT INTO foreshadowing (content, chapter_created, importance, status) VALUES ('高重要度伏笔', 1, 9, 'active')")
        cursor.execute("INSERT INTO foreshadowing (content, chapter_created, importance, status) VALUES ('已解决伏笔', 50, 7, 'resolved')")
        conn.commit()
        conn.close()

        tool = ChapterMaintenanceTool(db_path=str(db_path))

        result = tool._check_foreshadowing_health(current_chapter=150)

        assert "active_count" in result
        assert "high_importance_count" in result
        assert "stale_hooks_count" in result

        print(f"✓ 活跃伏笔: {result['active_count']}")
        print(f"✓ 高重要度伏笔: {result['high_importance_count']}")
        print(f"✓ 过期伏笔: {result['stale_hooks_count']}")

        # 验证过期伏笔检测（chapter 1和150相差149，超过100章）
        assert result["stale_hooks_count"] >= 1

    print("✅ 伏笔健康度检查测试通过\n")


def test_statistics_generation():
    """测试统计数据生成"""
    print("\n=== 测试统计数据生成 ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        setup_test_database(str(db_path))

        tool = ChapterMaintenanceTool(db_path=str(db_path))

        result = tool._generate_statistics(current_chapter=100)

        assert "chapter_count" in result
        assert "character_count" in result
        assert "event_count" in result
        assert "change_logs" in result
        assert "foreshadowing" in result
        assert "recent_metrics" in result

        print(f"✓ 章节数: {result['chapter_count']}")
        print(f"✓ 角色数: {result['character_count']}")
        print(f"✓ 事件数: {result['event_count']}")
        print(f"✓ 变更日志: {result['change_logs']['total']}")

    print("✅ 统计数据生成测试通过\n")


if __name__ == "__main__":
    test_should_run_maintenance()
    test_database_optimization()
    test_foreshadowing_health()
    test_statistics_generation()
    test_run_maintenance()

    print("=" * 60)
    print("✅ 所有章节维护工具测试通过")
    print("=" * 60)
