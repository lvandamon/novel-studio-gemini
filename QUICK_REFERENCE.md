# Novel Studio Gemini - 快速参考卡

## 🚀 快速启动

```bash
# 1. 初始化
uv sync
uv run python utils/init_world_v2.py
uv run python utils/init_style.py

# 2. 健康检查
uv run python utils/integrity_check.py

# 3. 启动后端
cd backend && uv run uvicorn api.main:app --reload

# 4. 启动前端
cd frontend && npm run dev
```

---

## 🔧 常用命令

### 测试
```bash
# P1修复测试
uv run python tests/test_p1_fixes.py

# 完整测试套件
pytest tests/

# 工作流测试
uv run python tests/test_workflow_v2.py
```

### 数据库操作
```bash
# 完整性检查
uv run python utils/integrity_check.py

# JSON格式报告
uv run python utils/integrity_check.py --json > report.json

# 数据库备份
cp data/novel.db backups/novel_$(date +%Y%m%d_%H%M%S).db

# 查看数据库信息
sqlite3 data/novel.db "SELECT COUNT(*) FROM characters"
sqlite3 data/novel.db "SELECT COUNT(*) FROM events"
```

### Neo4j操作
```bash
# 健康检查
python -c "from core.graph_store import GraphManager; g = GraphManager(); print(g.health_check())"

# 图谱优化（归档旧事件）
python -c "from core.memory import MemoryManager; m = MemoryManager(); m.graph.optimize_graph(archive_before_chapter=500)"
```

---

## 📊 关键API

### 1. 时间线验证
```python
from core.world_consistency import WorldConsistencyEngine

engine = WorldConsistencyEngine(memory_manager)
violations = engine.validate_timeline(
    draft="一年后，主角闭关突破到元婴期。",
    current_date="天道历元年1月1日",
    chapter_num=100
)

for v in violations:
    print(f"[{v['severity']}] {v['detail']}")
```

### 2. 变更历史追踪
```python
# 记录物品损坏
memory.log_inventory_change(
    character_name="韩立",
    item_name="掌天瓶",
    chapter_num=150,
    change_type="DAMAGED",
    old_durability=100,
    new_durability=50,
    reason="遭受天劫攻击"
)

# 查询历史
history = memory.get_inventory_history(
    character_name="韩立",
    item_name="掌天瓶",
    chapter_from=100,
    chapter_to=200
)
```

### 3. 连接池使用
```python
# 方式1: 手动管理
conn = memory._get_connection()
try:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM characters")
finally:
    memory._return_connection(conn)

# 方式2: 上下文管理器（推荐）
with memory._connection_context() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM characters")
```

### 4. Retcon操作
```python
from agents.retcon_agent import RetconAgent

agent = RetconAgent(memory)

# 分析修正指令
plan = agent.analyze_retcon("将韩立的修为从筑基期改为结丹期")

# Dry run预览
logs = agent.execute_retcon(plan, dry_run=True)

# 执行修正
logs = agent.execute_retcon(plan, dry_run=False)
```

### 5. 完整性检查
```python
from utils.integrity_check import IntegrityChecker

checker = IntegrityChecker(db_path="data/novel.db")
report = checker.check_all()

if report["by_severity"]["error"] > 0:
    print("⚠️ 发现严重错误")
```

---

## 🎯 最佳实践

### 章节生成工作流

**生成前检查**:
```python
# 1. 验证章节连续性
assert current_chapter == last_chapter + 1

# 2. 检查活跃角色状态
for char in active_characters:
    status = memory.get_character(char)
    assert status is not None

# 3. 确认伏笔健康度
hooks = memory.get_active_hooks()
print(f"活跃伏笔数: {len(hooks)}")
```

**生成后验证**:
```python
# 1. 世界一致性检查
from core.world_consistency import WorldConsistencyEngine
engine = WorldConsistencyEngine(memory)
violations = engine.generate_report(
    draft=final_content,
    active_characters=active_chars,
    current_chapter=chapter_num,
    current_date=current_date
)

# 2. 提取数据验证
extraction = archivist.extract_chapter_data(final_content)
if extraction.extraction_confidence < 0.7:
    print("⚠️ 提取置信度过低，需人工复核")

# 3. 记录变更日志
# ... (在ArchivistAgent中自动调用)
```

### 每100章维护

```bash
#!/bin/bash
CHAPTER=$1

if [ $((CHAPTER % 100)) -eq 0 ]; then
    echo "🔧 执行第 ${CHAPTER} 章维护..."

    # 1. 完整性检查
    uv run python utils/integrity_check.py

    # 2. 数据库备份
    cp data/novel.db "backups/novel_ch${CHAPTER}.db"

    # 3. Neo4j优化
    python -c "from core.memory import MemoryManager; m = MemoryManager(); m.graph.optimize_graph(archive_before_chapter=$((CHAPTER-500)))"

    # 4. 伏笔健康度检查
    python -c "from core.memory import MemoryManager; m = MemoryManager(); hooks = m.get_active_hooks(); print(f'活跃伏笔: {len(hooks)}')"

    echo "✅ 维护完成"
fi
```

---

## 🐛 故障排查

### 问题1: 连接池耗尽
```
Exception: 连接池耗尽，请稍后重试
```

**解决方案**:
```python
# 检查是否有未归还的连接
pool = memory._connection_pool
print(f"活跃连接: {pool._created_connections}")

# 增加pool_size（在memory.py初始化时）
self._connection_pool = SQLiteConnectionPool(
    db_path=self.db_path,
    pool_size=10,  # 从5改为10
    timeout=30.0
)
```

### 问题2: 数据库锁定
```
sqlite3.OperationalError: database is locked
```

**解决方案**:
```python
# 1. 检查WAL模式
conn = sqlite3.connect("data/novel.db")
cursor = conn.cursor()
cursor.execute("PRAGMA journal_mode")
print(cursor.fetchone())  # 应输出 ('wal',)

# 2. 清理WAL文件
cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
```

### 问题3: Neo4j连接失败
```
Neo4j 不可用，回退到SQLite备份
```

**解决方案**:
```python
# 1. 检查环境变量
import os
print(os.getenv("NEO4J_URI"))
print(os.getenv("NEO4J_USER"))
print(os.getenv("NEO4J_PASSWORD"))

# 2. 手动重连
memory.graph._driver.close()
from core.graph_store import GraphManager
memory.graph = GraphManager()

# 3. 验证连接
if memory.graph.is_connected():
    print("✅ Neo4j已恢复")
```

### 问题4: 时间线验证误报
```
时间线跳跃: 文中提到'一年后'(约365天), 但缺少合理的时间流逝过渡描述
```

**调整方案**:
```python
# 编辑 backend/core/world_consistency.py

# 1. 扩展过渡关键词
transition_keywords = [
    "闭关", "修炼", "养伤", "疗伤", "静养",
    "潜修", "游历", "远行",
    # 新增
    "打坐", "调息", "炼丹", "闭死关", "苦修"
]

# 2. 调整跳跃阈值
if days_delta >= 60:  # 从30天改为60天
    # ...
```

---

## 📈 性能监控

### 关键指标
```python
import sqlite3

conn = sqlite3.connect("data/novel.db")
cursor = conn.cursor()

# 角色数
cursor.execute("SELECT COUNT(*) FROM characters")
print(f"角色数: {cursor.fetchone()[0]}")

# 事件数
cursor.execute("SELECT COUNT(*) FROM events")
print(f"事件数: {cursor.fetchone()[0]}")

# 章节数
cursor.execute("SELECT MAX(chapter_num) FROM events")
print(f"最新章节: {cursor.fetchone()[0]}")

# 变更日志数
cursor.execute("SELECT COUNT(*) FROM inventory_change_log")
print(f"物品变更: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM status_effect_log")
print(f"状态变更: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM body_status_log")
print(f"身体变更: {cursor.fetchone()[0]}")

# 伏笔统计
cursor.execute("SELECT status, COUNT(*) FROM foreshadowing GROUP BY status")
for status, count in cursor.fetchall():
    print(f"伏笔[{status}]: {count}")

conn.close()
```

### 数据库大小
```bash
# 查看文件大小
du -h data/novel.db
du -h data/novel.db-shm
du -h data/novel.db-wal

# 查看表大小（需要sqlite3）
sqlite3 data/novel.db "SELECT name, SUM(pgsize) as size FROM dbstat GROUP BY name ORDER BY size DESC LIMIT 10"
```

---

## 🔐 数据备份策略

### 自动备份脚本
```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="backups"
DB_PATH="data/novel.db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 创建备份目录
mkdir -p $BACKUP_DIR

# 备份数据库
cp $DB_PATH "$BACKUP_DIR/novel_${TIMESTAMP}.db"

# 压缩旧备份（保留最近10个）
ls -t $BACKUP_DIR/*.db | tail -n +11 | xargs -I {} gzip {}

echo "✅ 备份完成: novel_${TIMESTAMP}.db"
```

### 恢复备份
```bash
#!/bin/bash
# restore.sh

BACKUP_FILE=$1

if [ -z "$BACKUP_FILE" ]; then
    echo "用法: ./restore.sh backups/novel_20260118.db"
    exit 1
fi

# 备份当前数据库
cp data/novel.db data/novel.db.before_restore

# 恢复
cp $BACKUP_FILE data/novel.db

echo "✅ 已恢复: $BACKUP_FILE"
echo "原数据库备份在: data/novel.db.before_restore"
```

---

## 📚 重要文档

| 文档 | 说明 |
|-----|------|
| `P1_FIXES_SUMMARY.md` | P1修复详细报告 |
| `OPTIMIZATION_GUIDE.md` | 完整优化指南 |
| `CLAUDE.md` | 项目技术文档 |
| `GEMINI.md` | 项目需求文档 |
| `tests/test_p1_fixes.py` | P1测试套件 |
| `utils/integrity_check.py` | 完整性检查工具 |

---

## 🎓 培训建议

### 新手入门（1天）
1. 阅读 `CLAUDE.md` 了解项目架构
2. 运行 `test_p1_fixes.py` 熟悉核心功能
3. 执行 `integrity_check.py` 理解数据完整性
4. 查看 `OPTIMIZATION_GUIDE.md` 学习最佳实践

### 中级使用（1周）
1. 理解15个Agent的职责和交互
2. 掌握LangGraph工作流
3. 熟悉三层内存架构（SQLite + ChromaDB + Neo4j）
4. 学习Retcon机制和污点分析

### 高级优化（1个月）
1. 实现自定义Agent
2. 优化LLM Prompt
3. 调优数据库性能
4. 扩展世界一致性规则

---

## ⚡ 快捷键（CLI）

```python
# main.py 中的常用命令

/help              # 查看帮助
/status            # 查看系统状态
/generate [n]      # 生成第n章
/review [n]        # 复审第n章
/retcon [指令]     # 执行历史修正
/check             # 完整性检查
/backup            # 创建备份
/stats             # 查看统计信息
```

---

## 🌟 核心价值

✅ **一致性保障**: 时间线、物理、经济、锚点四维验证
✅ **可追溯性**: 完整的状态变更历史日志
✅ **稳定性**: 连接池、原子事务、降级机制
✅ **可维护性**: 完整性检查工具、自动备份
✅ **扩展性**: 支持1500-2000章（200万字）规模

---

**版本**: v2.1.0
**更新日期**: 2026-01-18
**支持邮箱**: novel-studio@example.com
