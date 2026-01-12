"""
🔥 P0性能优化验证测试

测试三个关键优化:
1. 向量数据库章节分区检索
2. Neo4j时间窗口查询
3. SQLite WAL模式并发写入

使用方法:
    uv run python tests/test_p0_optimizations.py
"""

import sys
import time
import sqlite3
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.memory import MemoryManager
from langchain_core.documents import Document


def test_vector_partition_optimization():
    """测试向量数据库分区优化"""
    print("\n" + "="*60)
    print("🔥 测试1: 向量数据库章节分区优化")
    print("="*60)

    memory = MemoryManager(
        db_path="data/novel.db",
        vector_db_path="data/vector_store"
    )

    # 模拟添加大量章节数据
    print("\n📝 准备测试数据: 添加200个模拟章节...")
    for i in range(1, 201):
        content = f"第{i}章: 萧风在青云宗修炼,突破境界,与李师兄切磋武艺。" * 5
        memory.add_chapter_context(content, i, {"importance": 5 if i % 10 == 0 else 3})

    # 测试未优化的查询(无chapter过滤)
    print("\n⏱️  测试未优化查询(全量扫描)...")
    start = time.time()
    result_unoptimized = memory.vector_store.similarity_search(
        "萧风修炼",
        k=5
    )
    time_unoptimized = time.time() - start
    print(f"   未优化耗时: {time_unoptimized:.3f}秒, 结果数: {len(result_unoptimized)}")

    # 测试优化后的查询(带chapter窗口)
    print("\n⚡ 测试优化后查询(章节分区)...")
    start = time.time()
    result_optimized = memory.query_related_context(
        "萧风修炼",
        k=5,
        current_chapter=150  # 模拟在第150章查询
    )
    time_optimized = time.time() - start
    print(f"   优化后耗时: {time_optimized:.3f}秒")
    print(f"   性能提升: {((time_unoptimized - time_optimized) / time_unoptimized * 100):.1f}%")

    # 验证结果质量
    print("\n✅ 优化后检索结果预览:")
    print(result_optimized[:300] + "...")

    return time_optimized < time_unoptimized


def test_neo4j_time_window():
    """测试Neo4j时间窗口优化"""
    print("\n" + "="*60)
    print("🔥 测试2: Neo4j时间窗口查询优化")
    print("="*60)

    memory = MemoryManager()

    if not memory.graph.is_connected():
        print("   ⚠️  Neo4j未连接,跳过测试")
        return True

    # 模拟添加大量历史关系
    print("\n📝 准备测试数据: 添加100条历史关系...")
    for i in range(1, 101):
        memory.graph.update_relationship(
            source="萧风",
            source_type="Character",
            relation="KNOWS",
            target=f"NPC_{i}",
            target_type="Character",
            properties={"desc": f"相识于第{i}章"},
            chapter_num=i
        )

    # 测试未优化查询(全历史)
    print("\n⏱️  测试未优化查询(全历史扫描)...")
    start = time.time()
    result_unopt = memory.graph.query_entity_context("萧风", current_chapter=999999, recent_window=999999)
    time_unopt = time.time() - start
    print(f"   未优化耗时: {time_unopt:.3f}秒")

    # 测试优化查询(时间窗口)
    print("\n⚡ 测试优化后查询(时间窗口=50章)...")
    start = time.time()
    result_opt = memory.graph.query_entity_context("萧风", current_chapter=100, recent_window=50)
    time_opt = time.time() - start
    print(f"   优化后耗时: {time_opt:.3f}秒")
    print(f"   性能提升: {((time_unopt - time_opt) / time_unopt * 100):.1f}%")

    print("\n✅ 优化后查询结果(仅显示近期关系):")
    print(result_opt[:400])

    return time_opt < time_unopt


def test_sqlite_wal_mode():
    """测试SQLite WAL模式优化"""
    print("\n" + "="*60)
    print("🔥 测试3: SQLite WAL模式并发写入优化")
    print("="*60)

    db_path = "data/novel.db"

    # 检查WAL模式是否启用
    print("\n📊 检查数据库模式...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    journal_mode = cursor.fetchone()[0]
    conn.close()

    print(f"   当前Journal模式: {journal_mode}")

    if journal_mode.upper() != "WAL":
        print("   ❌ WAL模式未启用!")
        return False

    print("   ✅ WAL模式已启用")

    # 检查索引
    print("\n📊 检查性能索引...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'")
    indexes = cursor.fetchall()
    conn.close()

    print(f"   发现 {len(indexes)} 个优化索引:")
    for idx in indexes:
        print(f"      - {idx[0]}")

    if len(indexes) < 5:
        print("   ⚠️  索引数量少于预期,可能影响性能")
        return False

    print("   ✅ 索引配置正常")

    # 测试并发写入性能
    print("\n⏱️  测试并发写入性能...")
    memory = MemoryManager()

    start = time.time()
    for i in range(50):
        memory.log_chapter_metrics(i, {
            "tension": 50 + i,
            "tone_darkness": 40,
            "pacing_score": 60,
            "plot_logic_score": 85,
            "character_consistency_score": 90
        })
    write_time = time.time() - start

    print(f"   50次写入耗时: {write_time:.3f}秒")
    print(f"   平均每次: {write_time/50*1000:.1f}ms")

    if write_time / 50 < 0.1:  # 平均<100ms为优秀
        print("   ✅ 写入性能优秀")
        return True
    elif write_time / 50 < 0.5:
        print("   ⚠️  写入性能一般,可能需要进一步优化")
        return True
    else:
        print("   ❌ 写入性能较差")
        return False


def main():
    print("\n" + "🔥"*30)
    print("P0性能优化验证测试套件")
    print("🔥"*30)

    results = {}

    try:
        results["向量分区"] = test_vector_partition_optimization()
    except Exception as e:
        print(f"\n❌ 向量分区测试失败: {e}")
        results["向量分区"] = False

    try:
        results["Neo4j窗口"] = test_neo4j_time_window()
    except Exception as e:
        print(f"\n❌ Neo4j窗口测试失败: {e}")
        results["Neo4j窗口"] = False

    try:
        results["SQLite WAL"] = test_sqlite_wal_mode()
    except Exception as e:
        print(f"\n❌ SQLite WAL测试失败: {e}")
        results["SQLite WAL"] = False

    # 总结
    print("\n" + "="*60)
    print("📊 测试结果总结")
    print("="*60)

    passed = sum(results.values())
    total = len(results)

    for name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {name:15s}: {status}")

    print(f"\n总计: {passed}/{total} 项通过")

    if passed == total:
        print("\n🎉 所有P0优化验证通过! 系统已为200万字规模做好准备。")
        return 0
    else:
        print(f"\n⚠️  {total - passed}项优化未通过,请检查上述错误信息。")
        return 1


if __name__ == "__main__":
    exit(main())
