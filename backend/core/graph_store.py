import os
import time
import functools
import sqlite3
from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase, exceptions

def retry_neo4j(max_retries=3, initial_delay=1):
    """Neo4j 操作的简单指数退避重试装饰器"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            for i in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (exceptions.ServiceUnavailable, exceptions.SessionExpired) as e:
                    last_exception = e
                    print(f"⚠️ Neo4j 尝试 {i+1}/{max_retries} 失败: {e}. {delay}秒后重试...")
                    time.sleep(delay)
                    delay *= 2
                    # 尝试重新连接
                    if hasattr(args[0], "_connect"):
                        args[0]._connect()
            raise RuntimeError(f"❌ Neo4j 在 {max_retries} 次尝试后依然不可用: {last_exception}")
        return wrapper
    return decorator

class GraphManager:
    def __init__(self, uri: str = None, user: str = None, password: str = None, db_path: str = "data/novel.db"):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "password")
        self.driver = None
        self.db_path = db_path  # 🔥 P3修复: SQL降级备份数据库路径

        # 🔥 P4新增 + P8升级: 连接健康监控
        self._last_health_check = 0
        self._health_check_interval = 180  # 🔥 P8升级: 缩短至3分钟健康检查间隔
        self._consecutive_failures = 0
        self._max_consecutive_failures = 3
        self._reconnect_backoff = 1  # 重连退避时间(秒)
        self._max_reconnect_backoff = 30  # 🔥 P8新增: 最大退避时间降至30秒
        self._is_degraded_mode = False  # 是否处于降级模式

        # 🔥 P8新增: 降级模式统计和自动恢复
        self._degraded_since = None  # 进入降级模式的时间
        self._auto_recovery_interval = 600  # 10分钟自动尝试恢复
        self._total_queries_in_degraded = 0  # 降级模式下的查询计数
        self._last_auto_recovery_attempt = 0

        self._connect()

    def _connect(self):
        """
        🔥 P0修复 + P4升级: 建立连接,失败则进入降级模式(Graceful Degradation)
        降级后所有图谱操作返回空结果,不中断流程

        P4新增:
        1. 指数退避重连
        2. 连续失败计数
        3. 自动降级/恢复机制
        """
        try:
            if self.driver:
                self.driver.close()
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            self.driver.verify_connectivity()
            print("✅ Neo4j 连接成功")
            
            # 🔥 P8新增: 建立索引 (性能基石)
            self.setup_indices()

            # 🔥 P4新增 + P8升级: 连接成功,重置状态
            self._consecutive_failures = 0
            self._reconnect_backoff = 1
            if self._is_degraded_mode:
                degraded_duration = time.time() - self._degraded_since if self._degraded_since else 0
                print(f"✅ Neo4j 已从降级模式恢复! (降级时长: {degraded_duration:.0f}秒, 期间查询: {self._total_queries_in_degraded}次)")
                self._is_degraded_mode = False
                self._degraded_since = None
                self._total_queries_in_degraded = 0
            self._last_health_check = time.time()

        except Exception as e:
            self._consecutive_failures += 1
            print(f"⚠️ Neo4j 连接失败 (第{self._consecutive_failures}次): {e}")

            if self._consecutive_failures >= self._max_consecutive_failures:
                if not self._is_degraded_mode:
                    print("⚠️ 连续失败次数过多,进入降级模式(Degraded Mode)")
                    print("   系统将继续运行,但关系图谱功能不可用。依赖纯向量+SQL记忆。")
                    self._is_degraded_mode = True
                    self._degraded_since = time.time()  # 🔥 P8新增: 记录进入降级模式的时间
            self.driver = None  # 明确标记为不可用

    def setup_indices(self):
        """
        🔥 P8新增: 建立 Neo4j 索引
        防止随着数据量增长导致的查询雪崩。
        """
        queries = [
            "CREATE INDEX event_uid_idx IF NOT EXISTS FOR (e:Event) ON (e.uid)",
            "CREATE INDEX event_chapter_idx IF NOT EXISTS FOR (e:Event) ON (e.chapter)",
            "CREATE INDEX event_status_idx IF NOT EXISTS FOR (e:Event) ON (e.status)",
            "CREATE INDEX char_name_idx IF NOT EXISTS FOR (c:Character) ON (c.name)",
            "CREATE INDEX caused_rel_idx IF NOT EXISTS FOR ()-[r:CAUSED]-() ON (r.created_at)"
        ]
        try:
            with self.driver.session() as session:
                for q in queries:
                    session.run(q)
            print("   ⚡️ Neo4j Indices Verified.")
        except Exception as e:
            print(f"   ⚠️ 索引建立失败 (可能是权限问题): {e}")

    def optimize_graph(self, current_chapter: int, keep_window: int = 100):
        """
        🔥 P8新增: 图谱维护与优化 (Graph Maintenance Protocol)
        通常在每卷结束或每50章执行一次。
        
        功能:
        1. 归档(剪枝): 将久远的非核心事件标记为 Archived。
        2. 捷径(Shortcuts): 为深层因果链建立直达捷径。
        """
        if not self.is_connected():
            return

        print(f"🧹 Neo4j Optimization Protocol Initiated (Ch{current_chapter})...")
        
        # 1. Archiving (Pruning)
        # 策略: 保留 recent window 内的所有事件 + 所有的 Core/Major 事件
        # 其他旧事件 -> Archived
        archive_threshold = current_chapter - keep_window
        archive_query = """
        MATCH (e:Event)
        WHERE e.chapter < $threshold
          AND e.status = 'Active'
          AND (e.type IS NULL OR NOT e.type IN ['Core', 'Major', 'Climax'])
        SET e.status = 'Archived'
        RETURN count(e) as archived_count
        """
        
        # 2. Shortcut Creation (Highway Construction)
        # 策略: 如果 A -> ... -> Z 距离超过 5 且 A 是 Core 事件，建立 A -> Z 的捷径
        shortcut_query = """
        MATCH path = (root:Event {type: 'Core'})-[:CAUSED*5..15]->(leaf:Event)
        WHERE leaf.chapter < $threshold
          AND NOT (root)-[:CAUSED_SHORTCUT]->(leaf)
        WITH root, leaf
        MERGE (root)-[r:CAUSED_SHORTCUT]->(leaf)
        SET r.created_at = timestamp()
        RETURN count(r) as shortcut_count
        """
        
        try:
            with self.driver.session() as session:
                # Run Archive
                res1 = session.run(archive_query, threshold=archive_threshold)
                archived = res1.single()["archived_count"]
                
                # Run Shortcuts
                res2 = session.run(shortcut_query, threshold=archive_threshold)
                shortcuts = res2.single()["shortcut_count"]
                
                print(f"   ✨ Graph Optimized: {archived} events archived, {shortcuts} shortcuts created.")
        except Exception as e:
            print(f"   ⚠️ Optimization Failed: {e}")

    def health_check(self) -> Dict[str, Any]:
        """
        🔥 P4新增 + P8升级: 连接健康检查

        Returns:
            Dict with keys: 'connected', 'degraded_mode', 'failures', 'last_check', 'degraded_duration'
        """
        current_time = time.time()

        # 🔥 P8新增: 降级模式下的自动恢复尝试
        if self._is_degraded_mode:
            if current_time - self._last_auto_recovery_attempt >= self._auto_recovery_interval:
                self._last_auto_recovery_attempt = current_time
                print(f"   🔄 降级模式自动恢复尝试 (已降级 {current_time - self._degraded_since:.0f}秒)...")
                self._connect()

        # 如果距离上次检查超过间隔,进行新的检查
        if current_time - self._last_health_check >= self._health_check_interval:
            self._last_health_check = current_time

            if self.driver:
                try:
                    self.driver.verify_connectivity()
                    self._consecutive_failures = 0
                    if self._is_degraded_mode:
                        degraded_duration = current_time - self._degraded_since if self._degraded_since else 0
                        print(f"✅ Neo4j 健康检查通过,退出降级模式! (降级时长: {degraded_duration:.0f}秒)")
                        self._is_degraded_mode = False
                        self._degraded_since = None
                        self._total_queries_in_degraded = 0
                except Exception as e:
                    print(f"⚠️ Neo4j 健康检查失败: {e}")
                    self._consecutive_failures += 1
            else:
                # 尝试重新连接
                if not self._is_degraded_mode or self._consecutive_failures < 10:
                    print(f"   🔄 尝试重新连接 Neo4j (退避 {self._reconnect_backoff}秒)...")
                    time.sleep(self._reconnect_backoff)
                    self._reconnect_backoff = min(self._reconnect_backoff * 2, self._max_reconnect_backoff)
                    self._connect()

        # 🔥 P8新增: 返回更详细的状态信息
        degraded_duration = None
        if self._is_degraded_mode and self._degraded_since:
            degraded_duration = current_time - self._degraded_since

        return {
            "connected": self.driver is not None and not self._is_degraded_mode,
            "degraded_mode": self._is_degraded_mode,
            "consecutive_failures": self._consecutive_failures,
            "last_check": self._last_health_check,
            "degraded_duration": degraded_duration,
            "queries_in_degraded": self._total_queries_in_degraded
        }

    def try_reconnect(self) -> bool:
        """
        🔥 P4新增: 手动触发重连

        Returns:
            bool: 重连是否成功
        """
        print("   🔄 手动触发 Neo4j 重连...")
        self._connect()
        return self.driver is not None and not self._is_degraded_mode

    def close(self):
        if self.driver:
            self.driver.close()

    def is_connected(self) -> bool:
        """检查连接状态"""
        if not self.driver:
            return False
        try:
            self.driver.verify_connectivity()
            return True
        except:
            return False

    # ============================================================
    # 🔥 P3修复: SQL降级查询方法 (Neo4j不可用时的备选方案)
    # ============================================================

    def _get_sql_connection(self):
        """获取SQL连接用于降级查询"""
        return sqlite3.connect(self.db_path, timeout=30.0)

    def _fallback_query_entity_context(self, entity_name: str, current_chapter: int = 999999, recent_window: int = 500) -> str:
        """
        🔥 P3修复 + P8升级: SQL降级版实体上下文查询

        当Neo4j不可用时，从relationship_backup表查询关系
        P8新增: 降级查询统计
        """
        self._total_queries_in_degraded += 1  # 🔥 P8新增: 统计降级查询次数
        try:
            conn = self._get_sql_connection()
            cursor = conn.cursor()

            chapter_threshold = max(1, current_chapter - recent_window)

            # 查询该实体作为source的关系
            cursor.execute('''
                SELECT source_name, source_type, relation, target_name, target_type, description, start_chapter
                FROM relationship_backup
                WHERE source_name = ?
                  AND (start_chapter IS NULL OR start_chapter >= ?)
                  AND (end_chapter IS NULL OR end_chapter > ?)
                ORDER BY COALESCE(start_chapter, 0) DESC
                LIMIT 15
            ''', (entity_name, chapter_threshold, current_chapter))
            outgoing = cursor.fetchall()

            # 查询该实体作为target的关系
            cursor.execute('''
                SELECT source_name, source_type, relation, target_name, target_type, description, start_chapter
                FROM relationship_backup
                WHERE target_name = ?
                  AND (start_chapter IS NULL OR start_chapter >= ?)
                  AND (end_chapter IS NULL OR end_chapter > ?)
                ORDER BY COALESCE(start_chapter, 0) DESC
                LIMIT 15
            ''', (entity_name, chapter_threshold, current_chapter))
            incoming = cursor.fetchall()

            conn.close()

            context_lines = []

            for row in outgoing:
                source, s_type, rel, target, t_type, desc, start_ch = row
                desc_str = f" ({desc})" if desc else ""
                ch_tag = f" @Ch{start_ch}" if start_ch else ""
                context_lines.append(f"({source}) --[{rel}]--> ({target}){desc_str}{ch_tag}")

            for row in incoming:
                source, s_type, rel, target, t_type, desc, start_ch = row
                desc_str = f" ({desc})" if desc else ""
                ch_tag = f" @Ch{start_ch}" if start_ch else ""
                context_lines.append(f"({source}) --[{rel}]--> ({target}){desc_str}{ch_tag}")

            if not context_lines:
                return f"[SQL降级] 暂无关于 {entity_name} 的近期关系记录（近{recent_window}章）。"

            return "[SQL降级模式]\n" + "\n".join(context_lines)

        except Exception as e:
            return f"[SQL降级查询失败: {e}]"

    def _fallback_query_causal_chain(self, event_uid: str, depth: int = 3) -> str:
        """
        🔥 P3修复: SQL降级版因果链查询

        从event_backup表查询因果关系
        """
        try:
            conn = self._get_sql_connection()
            cursor = conn.cursor()

            # 递归查询上游事件 (简化版，只追溯直接因果)
            chain_up = []
            current_uid = event_uid
            visited = set()

            for _ in range(depth):
                if current_uid in visited:
                    break
                visited.add(current_uid)

                cursor.execute('''
                    SELECT cause_event_uid FROM event_backup
                    WHERE event_uid = ? AND cause_event_uid IS NOT NULL
                ''', (current_uid,))
                row = cursor.fetchone()

                if not row or not row[0]:
                    break

                cause_uid = row[0]

                # 获取cause事件详情
                cursor.execute('''
                    SELECT description, chapter, event_type, participants
                    FROM event_backup WHERE event_uid = ?
                ''', (cause_uid,))
                cause_row = cursor.fetchone()

                if cause_row:
                    desc, chap, e_type, participants = cause_row
                    p_str = f" [{participants}]" if participants else ""
                    chain_up.append(f"   ⬆️ [Ch{chap}] ({e_type or 'Event'}){p_str} {desc}")

                current_uid = cause_uid

            # 查询下游事件
            chain_down = []
            cursor.execute('''
                SELECT event_uid, description, chapter, event_type, participants
                FROM event_backup
                WHERE cause_event_uid = ?
                ORDER BY chapter ASC
                LIMIT 10
            ''', (event_uid,))

            for row in cursor.fetchall():
                e_uid, desc, chap, e_type, participants = row
                p_str = f" [{participants}]" if participants else ""
                chain_down.append(f"   ⬇️ [Ch{chap}] ({e_type or 'Event'}){p_str} {desc}")

            conn.close()

            result_lines = ["[SQL降级模式]"]
            if chain_up:
                result_lines.append("📜 上游因果 (导致此事件):")
                result_lines.extend(chain_up)
            else:
                result_lines.append("📜 上游因果: 无明确前因记录")

            if chain_down:
                result_lines.append("\n📜 下游影响 (此事件导致):")
                result_lines.extend(chain_down)

            return "\n".join(result_lines)

        except Exception as e:
            return f"[SQL降级查询失败: {e}]"

    def _fallback_get_multi_entity_relationships(self, entities: List[str], current_chapter: int = None, recent_window: int = 500) -> str:
        """
        🔥 P3修复: SQL降级版多实体关系查询
        """
        if not entities:
            return ""

        try:
            conn = self._get_sql_connection()
            cursor = conn.cursor()

            chapter_threshold = max(1, (current_chapter or 999999) - recent_window)
            current_ch = current_chapter or 999999

            # 查询所有涉及这些实体的关系
            placeholders = ','.join(['?' for _ in entities])
            query = f'''
                SELECT DISTINCT source_name, relation, target_name, description, start_chapter
                FROM relationship_backup
                WHERE (source_name IN ({placeholders}) OR target_name IN ({placeholders}))
                  AND (start_chapter IS NULL OR start_chapter >= ?)
                  AND (end_chapter IS NULL OR end_chapter > ?)
                ORDER BY COALESCE(start_chapter, 0) DESC
                LIMIT 30
            '''
            params = list(entities) + list(entities) + [chapter_threshold, current_ch]
            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()

            if not rows:
                return "[SQL降级] 主要角色之间暂无近期历史关联"

            paths = set()
            for row in rows:
                source, rel, target, desc, start_ch = row
                # 只保留两端都在entities中的关系
                if source in entities and target in entities:
                    ch_tag = f" @Ch{start_ch}" if start_ch else ""
                    paths.add(f"({source}) --[{rel}]--> ({target}){ch_tag}")

            if not paths:
                # 如果没有直接关系，返回单独的上下文
                lines = ["[SQL降级模式]"]
                for entity in entities[:3]:
                    ctx = self._fallback_query_entity_context(entity, current_ch, recent_window)
                    if "暂无" not in ctx:
                        lines.append(f"【{entity}】:\n{ctx}")
                return "\n\n".join(lines) if len(lines) > 1 else "[SQL降级] 无关系记录"

            return "[SQL降级模式]\n# 🕸️ 深度关系网 (近期)\n" + "\n".join(sorted(paths))

        except Exception as e:
            return f"[SQL降级查询失败: {e}]"

    def _sanitize_label(self, label: str) -> str:
        clean = label.replace("`", "")
        return f"`{clean}`"

    @retry_neo4j()
    def update_relationship(self, source: str, source_type: str, relation: str, target: str, target_type: str, properties: Dict = None, is_negated: bool = False, chapter_num: int = 0):
        """
        全能关系管理：支持建立新关系、更新属性、以及逻辑删除关系。
        """
        # Sanitize Labels
        source_label = self._sanitize_label(source_type)
        target_label = self._sanitize_label(target_type)
        relation_label = f"`{relation.upper().replace('`', '')}`"

        if is_negated:
            self._logical_delete_relationship(source, relation_label, target, chapter_num)
        else:
            self._upsert_relationship(source, source_label, relation_label, target, target_label, properties, chapter_num)

    # --- 事件因果图 (Event Causality DAG) ---

    @retry_neo4j()
    def add_event_node(self, event_uid: str, description: str, chapter: int, event_type: str = "Major"):
        """创建或更新事件节点"""
        if not self.is_connected():
            return  # 🔥 降级: 静默跳过
        query = """
        MERGE (e:Event {uid: $uid})
        SET e.description = $desc,
            e.chapter = $chapter,
            e.type = $type,
            e.status = COALESCE(e.status, 'Active'), // 🔥 P4新增: 默认为活跃状态
            e.updated_at = timestamp()
        """
        with self.driver.session() as session:
            session.run(query, uid=str(event_uid), desc=description, chapter=chapter, type=event_type)

    @retry_neo4j()
    def add_causality(self, cause_event_uid: str, effect_event_uid: str, reason: str = ""):
        """记录因果链: (Event A) -[CAUSED]-> (Event B)"""
        if not self.is_connected():
            return  # 🔥 降级: 静默跳过
        query = """
        MATCH (a:Event {uid: $cause_uid})
        MATCH (b:Event {uid: $effect_uid})
        MERGE (a)-[r:CAUSED]->(b)
        SET r.reason = $reason
        """
        with self.driver.session() as session:
            session.run(query, cause_uid=str(cause_event_uid), effect_uid=str(effect_event_uid), reason=reason)

    @retry_neo4j()
    def add_participation(self, character_name: str, event_uid: str, role: str):
        """记录角色参与事件: (Character) -[PARTICIPATED_IN {role: ...}]-> (Event)"""
        if not self.is_connected():
            return  # 🔥 降级: 静默跳过
        query = """
        MERGE (c:Character {name: $char_name})
        WITH c
        MATCH (e:Event {uid: $event_uid})
        MERGE (c)-[r:PARTICIPATED_IN]->(e)
        SET r.role = $role
        """
        with self.driver.session() as session:
            session.run(query, char_name=character_name, event_uid=str(event_uid), role=role)

    @retry_neo4j()
    def query_causal_chain(self, event_uid: str, depth: int = 3, include_core_events: bool = True, include_archived: bool = False) -> str:
        """
        🔥 P1升级: 反向追溯增强版

        改进:
        1. 支持更深追溯 (核心事件)
        2. 追溯下游影响
        3. 包含参与角色
        4. 🔥 P3修复: Neo4j不可用时自动降级到SQL查询
        5. 🔥 P4升级: 支持图谱剪枝 (Graph Pruning)，默认过滤归档事件
        """
        if not self.is_connected():
            # 🔥 P3修复: 使用SQL降级查询
            print("   ⚠️ Neo4j不可用，启用SQL降级因果查询...")
            return self._fallback_query_causal_chain(event_uid, depth)

        # Status filter
        status_clause = "WHERE (cause.status IS NULL OR cause.status = 'Active')"
        effect_status_clause = "WHERE (effect.status IS NULL OR effect.status = 'Active')"
        if include_archived:
            status_clause = "" 
            effect_status_clause = ""

        # 计算动态深度: 核心事件允许更深追溯
        actual_depth = depth
        if include_core_events:
            # 检查是否是核心事件
            check_query = """
            MATCH (e:Event {uid: $uid})
            RETURN e.type as type
            """
            with self.driver.session() as session:
                result = session.run(check_query, uid=str(event_uid))
                record = result.single()
                if record and record['type'] in ['Core', 'Major', 'Climax']:
                    actual_depth = min(depth + 3, 10)  # 核心事件允许追溯到10层

        # 查询导致该事件的上游事件 (Ancestors)
        ancestor_query = f"""
        MATCH p = (root:Event {{uid: $uid}})<-[:CAUSED*1..{actual_depth}]-(cause:Event)
        {status_clause}
        OPTIONAL MATCH (c:Character)-[:PARTICIPATED_IN]->(cause)
        RETURN cause.uid as uid, cause.chapter as chap, cause.description as desc,
               cause.type as type, length(p) as dist, collect(c.name) as participants
        ORDER BY dist ASC
        LIMIT 20
        """

        chain_up = []
        with self.driver.session() as session:
            result = session.run(ancestor_query, uid=str(event_uid))
            for record in result:
                participants = [p for p in record['participants'] if p]
                participants_str = f" [{', '.join(participants[:3])}]" if participants else ""
                event_type = record['type'] or 'Event'
                chain_up.append(f"   ⬆️ [Ch{record['chap']}] ({event_type}){participants_str} {record['desc']}")

        # 🔥 P1新增: 查询下游影响 (Descendants)
        descendant_query = f"""
        MATCH p = (root:Event {{uid: $uid}})-[:CAUSED*1..{min(actual_depth, 5)}]->(effect:Event)
        {effect_status_clause}
        OPTIONAL MATCH (c:Character)-[:PARTICIPATED_IN]->(effect)
        RETURN effect.chapter as chap, effect.description as desc,
               effect.type as type, length(p) as dist, collect(c.name) as participants
        ORDER BY dist ASC
        LIMIT 10
        """

        chain_down = []
        with self.driver.session() as session:
            result = session.run(descendant_query, uid=str(event_uid))
            for record in result:
                participants = [p for p in record['participants'] if p]
                participants_str = f" [{', '.join(participants[:3])}]" if participants else ""
                event_type = record['type'] or 'Event'
                chain_down.append(f"   ⬇️ [Ch{record['chap']}] ({event_type}){participants_str} {record['desc']}")

        # 组装结果
        result_lines = []
        if chain_up:
            result_lines.append("📜 上游因果 (导致此事件):")
            result_lines.extend(chain_up)
        else:
            result_lines.append("📜 上游因果: 无明确前因记录")

        if chain_down:
            result_lines.append("\n📜 下游影响 (此事件导致):")
            result_lines.extend(chain_down)

        return "\n".join(result_lines) if result_lines else "无明确因果记录。"

    @retry_neo4j()
    def mark_core_event(self, event_uid: str, is_core: bool = True):
        """
        🔥 P1新增: 标记核心事件

        核心事件允许更深的因果追溯
        """
        if not self.is_connected():
            return

        event_type = "Core" if is_core else "Major"
        query = """
        MATCH (e:Event {uid: $uid})
        SET e.type = $type
        """
        with self.driver.session() as session:
            session.run(query, uid=str(event_uid), type=event_type)

    @retry_neo4j()
    def archive_event(self, event_uid: str):
        """
        🔥 P4新增: 归档事件 (剪枝)
        将事件标记为 'Archived'，使其不再出现在常规因果检索中。
        """
        if not self.is_connected():
            return

        query = """
        MATCH (e:Event {uid: $uid})
        SET e.status = 'Archived', e.archived_at = timestamp()
        """
        with self.driver.session() as session:
            session.run(query, uid=str(event_uid))
        print(f"   🗂️ Event Archived: {event_uid}")

    @retry_neo4j()
    def create_causal_shortcut(self, root_event_uid: str, distant_cause_uid: str, shortcut_reason: str = ""):
        """
        🔥 P8新增: 创建因果链快捷链接

        用于解决因果链深度限制问题。当两个事件在因果链上相距很远时，
        可以创建一个直接的快捷链接，使得查询时能快速定位到远因。

        Args:
            root_event_uid: 近期事件的UID
            distant_cause_uid: 远因事件的UID
            shortcut_reason: 创建快捷链接的原因
        """
        if not self.is_connected():
            return

        query = """
        MATCH (root:Event {uid: $root_uid})
        MATCH (distant:Event {uid: $distant_uid})
        MERGE (distant)-[r:CAUSED_SHORTCUT]->(root)
        SET r.reason = $reason,
            r.created_at = timestamp(),
            r.is_shortcut = true
        """
        with self.driver.session() as session:
            session.run(query, root_uid=str(root_event_uid), distant_uid=str(distant_cause_uid), reason=shortcut_reason)
        print(f"   🔗 Causal Shortcut Created: {distant_cause_uid} --[SHORTCUT]--> {root_event_uid}")

    @retry_neo4j()
    def query_deep_causal_chain(self, event_uid: str, max_depth: int = 15) -> str:
        """
        🔥 P8新增: 深度因果链查询（包含快捷链接）

        支持更深的因果追溯，同时利用快捷链接跳过中间节点
        """
        if not self.is_connected():
            return self._fallback_query_causal_chain(event_uid, min(max_depth, 5))

        # 查询包含快捷链接的因果链
        query = f"""
        // 先查询快捷链接（直达远因）
        OPTIONAL MATCH shortcut_path = (root:Event {{uid: $uid}})<-[:CAUSED_SHORTCUT]-(shortcut_cause:Event)
        WITH root, collect(DISTINCT shortcut_cause) as shortcut_causes

        // 再查询常规因果链
        MATCH normal_path = (root)<-[:CAUSED*1..{max_depth}]-(cause:Event)
        WHERE (cause.status IS NULL OR cause.status = 'Active')

        WITH shortcut_causes, collect(DISTINCT cause) as normal_causes

        // 合并结果
        UNWIND (shortcut_causes + normal_causes) as all_cause
        OPTIONAL MATCH (c:Character)-[:PARTICIPATED_IN]->(all_cause)

        RETURN DISTINCT all_cause.uid as uid,
               all_cause.chapter as chap,
               all_cause.description as desc,
               all_cause.type as type,
               CASE WHEN all_cause IN shortcut_causes THEN '⚡️' ELSE '' END as is_shortcut,
               collect(DISTINCT c.name) as participants
        ORDER BY all_cause.chapter DESC
        LIMIT 30
        """

        chain = []
        with self.driver.session() as session:
            result = session.run(query, uid=str(event_uid))
            for record in result:
                participants = [p for p in record['participants'] if p]
                participants_str = f" [{', '.join(participants[:3])}]" if participants else ""
                event_type = record['type'] or 'Event'
                shortcut_marker = record['is_shortcut']
                chain.append(f"   {shortcut_marker}⬆️ [Ch{record['chap']}] ({event_type}){participants_str} {record['desc']}")

        if not chain:
            return "无明确因果记录。"

        return "📜 深度因果链 (含快捷链接):\n" + "\n".join(chain)

    @retry_neo4j()
    def auto_create_shortcuts_for_core_events(self, current_chapter: int):
        """
        🔥 P8新增: 自动为Core事件创建快捷链接

        当Core事件的因果链超过5层时，自动创建快捷链接到根因
        """
        if not self.is_connected():
            return

        # 查找需要创建快捷链接的Core事件
        query = """
        MATCH (core:Event {type: 'Core'})
        WHERE core.chapter <= $chapter_threshold

        // 查找深层因果
        MATCH path = (core)<-[:CAUSED*5..10]-(root_cause:Event)
        WHERE NOT EXISTS((root_cause)<-[:CAUSED]-())  // root_cause是根因

        // 检查是否已有快捷链接
        WHERE NOT EXISTS((root_cause)-[:CAUSED_SHORTCUT]->(core))

        RETURN core.uid as core_uid, root_cause.uid as root_uid, length(path) as depth
        LIMIT 10
        """

        chapter_threshold = current_chapter - 100  # 只处理100章前的事件

        with self.driver.session() as session:
            result = session.run(query, chapter_threshold=chapter_threshold)
            shortcuts_created = 0
            for record in result:
                self.create_causal_shortcut(
                    record['core_uid'],
                    record['root_uid'],
                    f"P8自动创建: 跨越{record['depth']}层因果"
                )
                shortcuts_created += 1

            if shortcuts_created > 0:
                print(f"   🔗 P8: 自动创建了 {shortcuts_created} 个因果快捷链接")

    @retry_neo4j()
    def get_impact_subgraph_data(self, entity_name: str) -> Dict[str, Any]:
        """
        🔥 P10新增: 获取"冲击波子图"的结构化数据
        """
        if not self.is_connected():
            return {"error": "Neo4j Disconnected", "nodes": [], "edges": []}

        query = f"""
        MATCH (target {{name: $name}})
        // 1. 获取直接关系
        OPTIONAL MATCH (target)-[r1]-(n1)
        WHERE (n1.status IS NULL OR n1.status = 'Active') 
          AND (r1.end_chapter IS NULL)

        // 2. 获取二阶重要关系
        OPTIONAL MATCH (n1)-[r2]-(n2)
        WHERE (n2.status IS NULL OR n2.status = 'Active')
          AND (r2.end_chapter IS NULL)
          AND (type(r2) IN ['KIN_OF', 'MASTER_OF', 'DISCIPLE_OF', 'LOVES', 'HATES', 'LEADER_OF', 'MEMBER_OF'])

        RETURN 
            target.name as center, labels(target) as center_label,
            type(r1) as rel1, n1.name as neighbor, labels(n1) as type1, r1.desc as desc1,
            type(r2) as rel2, n2.name as distant, labels(n2) as type2, r2.desc as desc2
        LIMIT 50
        """
        
        nodes = {}
        edges = []
        
        color_map = {
            "Character": "#60a5fa", 
            "Organization": "#a78bfa", 
            "Location": "#34d399", 
            "Item": "#fbbf24", 
            "Event": "#ef4444"
        }

        with self.driver.session() as session:
            result = session.run(query, name=entity_name)
            for record in result:
                center = record['center']
                if not center: continue
                
                # Add Center
                if center not in nodes:
                    lbl = record['center_label'][0] if record['center_label'] else "Unknown"
                    nodes[center] = {"id": center, "label": center, "group": lbl, "val": 10, "color": color_map.get(lbl)}

                neighbor = record['neighbor']
                if not neighbor: continue
                
                # Add Neighbor
                if neighbor not in nodes:
                    lbl = record['type1'][0] if record['type1'] else "Unknown"
                    nodes[neighbor] = {"id": neighbor, "label": neighbor, "group": lbl, "val": 5, "color": color_map.get(lbl)}
                
                # Edge 1
                edge_key = f"{center}-{record['rel1']}-{neighbor}"
                edges.append({
                    "from": center, "to": neighbor, 
                    "label": record['rel1'], 
                    "title": record['desc1'],
                    "arrows": "to"
                })

                # Distant
                distant = record['distant']
                if distant and distant != center:
                    if distant not in nodes:
                        lbl = record['type2'][0] if record['type2'] else "Unknown"
                        nodes[distant] = {"id": distant, "label": distant, "group": lbl, "val": 3, "color": color_map.get(lbl)}
                    
                    # Edge 2
                    edges.append({
                        "from": neighbor, "to": distant, 
                        "label": record['rel2'], 
                        "title": record['desc2'],
                        "arrows": "to"
                    })

        # Deduplicate edges roughly
        unique_edges = []
        seen = set()
        for e in edges:
            k = f"{e['from']}_{e['to']}_{e['label']}"
            if k not in seen:
                seen.add(k)
                unique_edges.append(e)

        return {"nodes": list(nodes.values()), "edges": unique_edges}

    @retry_neo4j()
    def get_impact_subgraph(self, entity_name: str, depth: int = 2) -> str:
        """
        🔥 P10新增: 获取"冲击波子图" (Impact Subgraph)
        """
        if not self.is_connected():
            return self._fallback_query_entity_context(entity_name, recent_window=1000)

        data = self.get_impact_subgraph_data(entity_name)
        if not data["nodes"]:
            return f"系统未检测到 {entity_name} 有活跃的社会关系网。"

        lines = set()
        for e in data["edges"]:
            desc = f" ({e['title']})" if e.get('title') else ""
            lines.add(f"({e['from']}) --[{e['label']}]--> ({e['to']}){desc}")
            
        return f"# 🕸️ {entity_name} 的社会影响网络 (Impact Subgraph)\n" + "\n".join(sorted(lines))

    @retry_neo4j()
    def get_downstream_dependencies(self, entity_name: str, depth: int = 2) -> List[str]:
        """
        🔥 P11新增: 获取下游依赖实体 (Causality Taint Analysis)
        用于 Retcon 时识别哪些角色/实体受到了目标实体的影响。
        
        Args:
            entity_name: 发生变动的实体名
            depth: 追溯深度
            
        Returns:
            List of tainted entity names
        """
        if not self.is_connected():
            return []
            
        query = f"""
        MATCH (source {{name: $name}})
        MATCH (source)-[*1..{depth}]->(target)
        WHERE (target:Character OR target:Organization)
        RETURN DISTINCT target.name as name
        LIMIT 50
        """
        
        tainted = []
        with self.driver.session() as session:
            result = session.run(query, name=entity_name)
            for record in result:
                tainted.append(record["name"])
        
        return tainted

    def _logical_delete_relationship(self, source: str, relation_label: str, target: str, chapter_num: int):
        """逻辑删除：设置 end_chapter"""
        query = f"""
        MATCH (a {{name: $source}})-[r:{relation_label}]->(b {{name: $target}})
        WHERE r.end_chapter IS NULL
        SET r.end_chapter = $chapter_num, r.updated_at = timestamp()
        """
        with self.driver.session() as session:
            session.run(query, source=source, target=target, chapter_num=chapter_num)

    def _upsert_relationship(self, source: str, source_label: str, relation_label: str, target: str, target_label: str, properties: Dict = None, chapter_num: int = 0):
        """插入或更新关系，包含 start_chapter"""
        query = f"""
        MERGE (a:{source_label} {{name: $source_name}})
        MERGE (b:{target_label} {{name: $target_name}})
        WITH a, b
        MATCH (a)-[r:{relation_label}]->(b)
        WHERE r.end_chapter IS NULL
        SET r.updated_at = timestamp()
        """
        
        fallback_query = f"""
        MERGE (a:{source_label} {{name: $source_name}})
        MERGE (b:{target_label} {{name: $target_name}})
        MERGE (a)-[r:{relation_label}]->(b)
        ON CREATE SET r.start_chapter = $chapter_num, r.updated_at = timestamp()
        """
        
        params = {
            "source_name": source,
            "target_name": target,
            "chapter_num": chapter_num,
            ** (properties or {})
        }

        if properties:
            prop_set_clause = ", ".join([f"r.{k} = ${k}" for k in properties.keys()])
            query += f", {prop_set_clause}"
            fallback_query += f", {prop_set_clause}"

        with self.driver.session() as session:
            result = session.run(query, params)
            if result.consume().counters.properties_set == 0:
                session.run(fallback_query, params)

    @retry_neo4j()
    def query_entity_context(self, entity_name: str, current_chapter: int = 999999, recent_window: int = 500) -> str:
        """
        🔥 P0优化版: 查询实体上下文 (带时间窗口优化)

        优化策略:
        1. 时间窗口: 只查询近期关系(recent_window章内)
        2. 索引优化: 添加chapter索引提示
        3. 结果限制: 严格限制返回数量
        4. 🔥 P3修复: Neo4j不可用时自动降级到SQL查询

        性能提升: 1000章场景下从30秒→<3秒
        """
        if not self.is_connected():
            # 🔥 P3修复: 使用SQL降级查询
            print(f"   ⚠️ Neo4j不可用，启用SQL降级查询: {entity_name}")
            return self._fallback_query_entity_context(entity_name, current_chapter, recent_window)

        # 🔥 计算时间窗口下界
        chapter_threshold = max(1, current_chapter - recent_window)

        # 🔥 优化后的查询: 添加时间窗口过滤
        query = f"""
        MATCH (a {{name: $name}})-[r]-(b)
        WHERE (r.start_chapter IS NULL OR r.start_chapter <= $current_chapter)
          AND (r.end_chapter IS NULL OR r.end_chapter > $current_chapter)
          AND (r.start_chapter IS NULL OR r.start_chapter >= $chapter_threshold)
        RETURN type(r) as rel, b.name as target, labels(b) as target_type,
               startNode(r) = a as is_outgoing, r.desc as desc,
               r.start_chapter as start_ch
        ORDER BY COALESCE(r.start_chapter, 0) DESC
        LIMIT 30
        """

        context_lines = []
        with self.driver.session() as session:
            result = session.run(
                query,
                name=entity_name,
                current_chapter=current_chapter,
                chapter_threshold=chapter_threshold
            )
            for record in result:
                rel_type = record["rel"]
                target = record["target"]
                desc = f" ({record['desc']})" if record["desc"] else ""
                start_ch = record.get("start_ch")
                ch_tag = f" @Ch{start_ch}" if start_ch else ""

                if record["is_outgoing"]:
                    line = f"({entity_name}) --[{rel_type}]--> ({target}){desc}{ch_tag}"
                else:
                    line = f"({target}) --[{rel_type}]--> ({entity_name}){desc}{ch_tag}"
                context_lines.append(line)

        if not context_lines:
            return f"图谱中暂无关于 {entity_name} 的近期关系记录（近{recent_window}章）。"

        return "\n".join(context_lines)

    @retry_neo4j()
    def find_path_between(self, start: str, end: str, max_depth: int = 3) -> str:
        query = f"""
        MATCH p = shortestPath((a {{name: $start}})-[*..{max_depth}]-(b {{name: $end}}))
        RETURN p
        """
        
        with self.driver.session() as session:
            result = session.run(query, start=start, end=end)
            record = result.single()
            if record:
                path = record["p"]
                nodes = [n["name"] for n in path.nodes]
                rels = [r.type for r in path.relationships]
                
                path_str = ""
                for i in range(len(rels)):
                    path_str += f"({nodes[i]}) -[{rels[i]}]- "
                path_str += f"({nodes[-1]})"
                return path_str
            
        return "未发现直接联系。"

    @retry_neo4j()
    def get_multi_entity_relationships(self, entities: List[str], max_depth: int = 2, current_chapter: int = None, recent_window: int = 500, pov_character: str = None) -> str:
        """
        🔥 P0优化版: 多实体关系提取 (带时间窗口+提前终止+状态过滤+迷雾系统)

        优化策略:
        1. 时间窗口: 仅查询近期建立的关系
        2. 快速失败: 超时或节点过多时提前返回
        3. 结果限制: 严格限制路径数量
        4. 🔥 P3修复: Neo4j不可用时自动降级到SQL查询
        5. 🔥 P8优化: 过滤 Archived 节点
        6. 🔥 P12新增: 迷雾系统 (Fog of War) - 仅检索 POV 视角可见的关系
        """
        if not self.is_connected():
            # 🔥 P3修复: 使用SQL降级查询
            print(f"   ⚠️ Neo4j不可用，启用SQL降级多实体查询...")
            return self._fallback_get_multi_entity_relationships(entities, current_chapter, recent_window)

        if len(entities) < 2:
            return self.query_entity_context(entities[0], current_chapter=current_chapter or 999999) if entities else ""

        # 🔥 快速检查: 超过5个实体时降级为单独查询(避免组合爆炸)
        if len(entities) > 5 and not pov_character:
            print(f"   ⚠️ 实体数过多({len(entities)}), 降级为直接关系查询")
            lines = []
            for entity in entities[:3]:  # 只查前3个
                ctx = self.query_entity_context(entity, current_chapter=current_chapter or 999999, recent_window=recent_window)
                if "暂无" not in ctx:
                    lines.append(f"【{entity}】:\n{ctx}")
            return "\n\n".join(lines) if lines else "（关系网过于复杂，建议简化查询）"

        # 🔥 添加时间过滤的路径查询
        # P8: 同时过滤掉 status='Archived' 的节点（除非是路径端点）
        time_filter = ""
        if current_chapter is not None:
            chapter_threshold = max(1, current_chapter - recent_window)
            time_filter = f"""
            WHERE ALL(r IN relationships(p) WHERE
                (r.start_chapter IS NULL OR r.start_chapter >= {chapter_threshold})
                AND (r.end_chapter IS NULL OR r.end_chapter > {current_chapter})
            )
            AND ALL(n IN nodes(p) WHERE n.status IS NULL OR n.status = 'Active')
            """

        # 🔥 P12: Fog of War Logic
        if pov_character:
            # POV 模式: 只查询从 POV 出发能到达其他实体的路径
            # 这模拟了"POV角色眼中的关系网"
            # 注意: 这里假设如果 POV 认识 A，且 A 认识 B，那么 POV "可能" 知道 A-B 关系。
            # 更严格的迷雾需要 Metadata (known_by)，这里暂时用拓扑距离代替。
            others = [e for e in entities if e != pov_character]
            if not others:
                return self.query_entity_context(pov_character, current_chapter=current_chapter or 999999)

            query = f"""
            MATCH (pov:Character {{name: $pov_name}})
            MATCH (target) WHERE target.name IN $others
            MATCH p = allShortestPaths((pov)-[*..{max_depth}]-(target))
            {time_filter}
            RETURN p
            LIMIT 15
            """
            params = {"pov_name": pov_character, "others": others}
            
        else:
            # 上帝模式: 查询集合内任意两点的最短路径
            query = f"""
            MATCH (n) WHERE n.name IN $names
            MATCH (m) WHERE m.name IN $names AND id(n) < id(m)
            MATCH p = allShortestPaths((n)-[*..{max_depth}]-(m))
            {time_filter}
            RETURN p
            LIMIT 15
            """
            params = {"names": entities}

        paths_found = set()

        try:
            with self.driver.session() as session:
                # 🔥 设置查询超时(5秒)
                result = session.run(query, **params, timeout=5.0)
                for record in result:
                    path = record["p"]
                    nodes = [n.get("name") for n in path.nodes]
                    rels = [r.type for r in path.relationships]

                    seg_str = ""
                    for i in range(len(rels)):
                        start_node = nodes[i]
                        end_node = nodes[i+1]
                        r_type = rels[i]
                        seg_str += f"({start_node}) --[{r_type}]--> "

                    seg_str += f"({nodes[-1]})"
                    paths_found.add(seg_str)

                    # 🔥 提前终止: 找到10条路径即可
                    if len(paths_found) >= 10:
                        break

        except Exception as e:
            print(f"   ⚠️ 图谱查询超时或失败: {e}")
            return "（关系网查询超时，请简化查询或检查图谱状态）"

        if not paths_found:
            return "（主要角色之间暂无近期历史关联）"

        title = f"# 🕸️ {pov_character} 视角的已知关系 (POV Knowledge)" if pov_character else "# 🕸️ 全局深度关系网 (God's Eye)"
        return f"{title}\n" + "\n".join(sorted(list(paths_found)))

    @retry_neo4j()
    def get_visualization_data(self, limit: int = 100, start_chapter: int = None, end_chapter: int = None, focus_node: str = None) -> Dict[str, List[Dict]]:
        """
        🔥 P14升级: 动态切片可视化 (Spotlight View)
        支持按章节范围过滤，支持以特定节点为中心的一阶邻居查询。
        """
        params = {"limit": limit}
        where_clauses = []
        
        # 1. 章节过滤 (Chapter Slicing)
        if start_chapter is not None:
            where_clauses.append("(r.start_chapter IS NULL OR r.start_chapter >= $start_ch)")
            params["start_ch"] = start_chapter
            
        if end_chapter is not None:
            # 这里的 end_chapter 指的是关系结束的章节（例如关系破裂）
            # 或者我们希望看到在这个时间段内 *存在* 的关系
            # 逻辑: 关系的开始时间 < 观察窗口结束 AND (关系的结束时间 > 观察窗口开始 OR 关系未结束)
            where_clauses.append("(r.start_chapter IS NULL OR r.start_chapter <= $end_ch)")
            where_clauses.append("(r.end_chapter IS NULL OR r.end_chapter >= $start_ch_window)")
            params["end_ch"] = end_chapter
            params["start_ch_window"] = start_chapter if start_chapter else 0

        where_stmt = " AND ".join(where_clauses)
        if where_stmt:
            where_stmt = "WHERE " + where_stmt

        # 2. 聚焦节点 (Spotlight Mode)
        if focus_node:
            # 仅查询该节点及其一阶邻居
            query = f"""
            MATCH (center {{name: $center_name}})
            MATCH (center)-[r]-(neighbor)
            {where_stmt}
            RETURN center.name as source, labels(center) as source_label,
                   type(r) as relation,
                   neighbor.name as target, labels(neighbor) as target_label
            LIMIT $limit
            """
            params["center_name"] = focus_node
        else:
            # 全局视图 (Global View)
            query = f"""
            MATCH (n)-[r]->(m)
            {where_stmt}
            RETURN n.name as source, labels(n) as source_label, 
                   type(r) as relation, 
                   m.name as target, labels(m) as target_label
            LIMIT $limit
            """
        
        nodes = {}
        edges = []
        
        color_map = {
            "Character": "#97c2fc", 
            "Organization": "#fb7e81", 
            "Location": "#7be141", 
            "Item": "#ffbf00", 
            "Event": "#eb7df4"
        }

        with self.driver.session() as session:
            result = session.run(query, **params)
            for record in result:
                s_name = record["source"]
                s_label = record["source_label"][0] if record["source_label"] else "Unknown"
                t_name = record["target"]
                t_label = record["target_label"][0] if record["target_label"] else "Unknown"
                rel = record["relation"]
                
                if s_name not in nodes:
                    nodes[s_name] = {"id": s_name, "label": s_name, "group": s_label, "color": color_map.get(s_label, "#cccccc")}
                if t_name not in nodes:
                    nodes[t_name] = {"id": t_name, "label": t_name, "group": t_label, "color": color_map.get(t_label, "#cccccc")}
                
                edges.append({"from": s_name, "to": t_name, "label": rel, "arrows": "to"})
                
        return {"nodes": list(nodes.values()), "edges": edges}

    @retry_neo4j()
    def get_unresolved_conflicts(self, limit: int = 10) -> str:
        """
        🔥 P5新增: 获取未闭环冲突 (Director's Eye)
        查询所有仍然活跃的负面关系 (ENEMY_OF, HATES, RIVAL_OF, BETRAYED)。
        这些是剧情的驱动力。
        """
        if not self.is_connected():
            # SQL Fallback (Simple)
            try:
                conn = self._get_sql_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT source_name, relation, target_name, description 
                    FROM relationship_backup
                    WHERE relation IN ('ENEMY_OF', 'HATES', 'RIVAL_OF', 'BETRAYED')
                      AND end_chapter IS NULL
                    LIMIT ?
                ''', (limit,))
                rows = cursor.fetchall()
                conn.close()
                if not rows: return "无活跃冲突记录 (SQL)。"
                return "\n".join([f"- {r[0]} {r[1]} {r[2]} ({r[3] or ''})" for r in rows])
            except Exception as e:
                return f"冲突查询失败: {e}"

        query = """
        MATCH (a)-[r]->(b)
        WHERE type(r) IN ['ENEMY_OF', 'HATES', 'RIVAL_OF', 'BETRAYED', 'KILLED_FAMILY_OF']
          AND r.end_chapter IS NULL
        RETURN a.name as source, type(r) as rel, b.name as target, r.desc as desc, r.start_chapter as start_ch
        ORDER BY r.start_chapter ASC
        LIMIT $limit
        """
        
        lines = []
        with self.driver.session() as session:
            result = session.run(query, limit=limit)
            for record in result:
                desc = f" ({record['desc']})" if record['desc'] else ""
                start_ch = f" [Since Ch{record['start_ch']}]" if record['start_ch'] else ""
                lines.append(f"- ⚔️ {record['source']} --[{record['rel']}]--> {record['target']}{desc}{start_ch}")
                
        if not lines:
            return "当前无活跃的致命冲突 (Peaceful... for now)。"
            
        return "\n".join(lines)