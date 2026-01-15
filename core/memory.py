from core.schemas import CharacterSchema, RealityLayer, ArcStatus, VolumeSchema, ArcSchema
import sqlite3
import json
import os
import uuid
import chromadb # Explicit import
from typing import List, Dict, Any, Optional
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from core.graph_store import GraphManager
from core.llm import get_deepseek_chat
from core.prompts import ENTITY_EXTRACTION_PROMPT

class MemoryManager:
    def __init__(self, db_path: str = "data/novel.db", vector_db_path: str = "data/vector_store"):
        self.db_path = db_path
        self.vector_db_path = vector_db_path

        # 🔥 P0优化: 连接配置优化
        self._connection_timeout = 30.0  # 超时时间

        # 确保数据目录存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(self.vector_db_path, exist_ok=True)

        # 1. 初始化 SQLite
        self._init_sqlite()

        # 2. 初始化 ChromaDB (🔥 P7优化: 使用显式 Client 管理生命周期)
        self.chroma_client = chromadb.PersistentClient(path=self.vector_db_path)
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        
        self.vector_store = Chroma(
            client=self.chroma_client,
            collection_name="novel_content",
            embedding_function=self.embeddings,
        )
        
        self.event_store = Chroma(
            client=self.chroma_client,
            collection_name="novel_events",
            embedding_function=self.embeddings,
        )

        # 🔥 P5新增: 高光时刻库 (Emotional Highlights)
        # 专门存储"原汁原味"的原文片段,用于对抗摘要的枯燥
        self.highlight_store = Chroma(
            client=self.chroma_client,
            collection_name="novel_highlights",
            embedding_function=self.embeddings,
        )
        
        # 3. 初始化 Knowledge Graph (Neo4j)
        self.graph = GraphManager()
        
        # 4. 初始化实体提取链 (LLM)
        self.extractor_chain = ENTITY_EXTRACTION_PROMPT | get_deepseek_chat() | StrOutputParser()

    def _init_sqlite(self):
        """
        🔥 P0优化版: 初始化 SQLite 表结构 - v2.0 UUID 重构版

        优化策略:
        1. 启用WAL模式: 支持并发读写,写入不阻塞读取
        2. 优化PRAGMA设置: 提升写入性能
        3. 添加索引: 加速常用查询
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 🔥 P0优化: 启用WAL模式 (Write-Ahead Logging)
        # 优势: 允许并发读写,写入性能提升5-10倍
        cursor.execute("PRAGMA journal_mode=WAL")
        
        # 🔥 P7修复: 强制清理残留 WAL，防止锁死
        try:
            cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except:
            pass # 忽略错误，尽力而为

        # 🔥 P0优化: 性能调优参数
        cursor.execute("PRAGMA synchronous=NORMAL")  # 平衡安全性与性能
        cursor.execute("PRAGMA cache_size=-64000")   # 64MB缓存
        cursor.execute("PRAGMA temp_store=MEMORY")   # 临时表存内存
        cursor.execute("PRAGMA mmap_size=268435456") # 256MB内存映射
        
        # 1. 角色核心表 (ID 为主键)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS characters (
                id TEXT PRIMARY KEY,
                name TEXT,
                data JSON,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 2. 角色别名映射表 (别名 -> ID)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS character_aliases (
                alias TEXT PRIMARY KEY,
                character_id TEXT,
                is_primary BOOLEAN DEFAULT 0,
                FOREIGN KEY(character_id) REFERENCES characters(id)
            )
        ''')
        
        # 物品表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS items (
                name TEXT PRIMARY KEY,
                data JSON,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 章节元数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chapters (
                chapter_num INTEGER PRIMARY KEY,
                title TEXT,
                summary TEXT
            )
        ''')

        # 事件日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_num INTEGER,
                character_name TEXT,
                event_type TEXT,
                description TEXT,
                layer TEXT DEFAULT 'Reality',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 伏笔管理表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS foreshadowing (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_created INTEGER,
                content TEXT,
                importance INTEGER DEFAULT 5, -- 1-10 (1:Flavor, 10:Core Mystery)
                tags TEXT, -- JSON list e.g. ["Identity", "Weapon"]
                status TEXT DEFAULT 'active',
                chapter_resolved INTEGER,
                notes TEXT,
                -- 🔥 P0新增: 人工确认队列
                pending_resolution BOOLEAN DEFAULT 0, -- 是否待人工确认回收
                resolution_chapter_proposed INTEGER, -- 系统提议的回收章节
                resolution_confidence REAL DEFAULT 0, -- 系统检测的置信度 (0-1)
                human_reviewed BOOLEAN DEFAULT 0, -- 是否已人工审核
                human_approved BOOLEAN, -- 人工审核结果 (NULL=未审核, 1=确认回收, 0=驳回)
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 全局叙事焦点表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS narrative_focus (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                current_volume TEXT,
                current_arc TEXT,
                current_beat TEXT,
                current_goal TEXT,
                current_conflict TEXT,
                current_theme TEXT DEFAULT '成长', -- 新增：当前卷/单元的核心母题
                thematic_echo_count INTEGER DEFAULT 0, -- 新增：母题回响计数
                -- 🔥 P2新增: 母题衰减机制
                last_echo_chapter INTEGER DEFAULT 0, -- 最后一次回响的章节
                arc_start_chapter INTEGER DEFAULT 1, -- 当前单元开始章节 (用于按单元重置)
                world_state_summary TEXT,
                chapters_since_last_beat INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                current_date TEXT DEFAULT '天道历元年1月1日'
            )
        ''')

        # 自动迁移：检查是否存在新字段，不存在则添加 (Simple Migration)
        try:
            cursor.execute('ALTER TABLE narrative_focus ADD COLUMN current_theme TEXT DEFAULT "成长"')
        except: pass
        try:
            cursor.execute('ALTER TABLE narrative_focus ADD COLUMN thematic_echo_count INTEGER DEFAULT 0')
        except: pass
        try:
            cursor.execute('ALTER TABLE narrative_focus ADD COLUMN last_echo_chapter INTEGER DEFAULT 0')
        except: pass
        try:
            cursor.execute('ALTER TABLE narrative_focus ADD COLUMN arc_start_chapter INTEGER DEFAULT 1')
        except: pass
        try:
            cursor.execute('ALTER TABLE narrative_focus ADD COLUMN pacing_directive TEXT DEFAULT "Normal"')
        except: pass

        # Foreshadowing Table Migrations
        try:
            cursor.execute('ALTER TABLE foreshadowing ADD COLUMN pending_resolution BOOLEAN DEFAULT 0')
        except: pass
        try:
            cursor.execute('ALTER TABLE foreshadowing ADD COLUMN resolution_chapter_proposed INTEGER')
        except: pass
        try:
            cursor.execute('ALTER TABLE foreshadowing ADD COLUMN resolution_confidence REAL DEFAULT 0')
        except: pass
        try:
            cursor.execute('ALTER TABLE foreshadowing ADD COLUMN human_reviewed BOOLEAN DEFAULT 0')
        except: pass
        try:
            cursor.execute('ALTER TABLE foreshadowing ADD COLUMN human_approved BOOLEAN')
        except: pass
        try:
            cursor.execute('ALTER TABLE foreshadowing ADD COLUMN importance INTEGER DEFAULT 5')
        except: pass
        try:
            cursor.execute('ALTER TABLE foreshadowing ADD COLUMN tags TEXT')
        except: pass

        # Style Guide Migrations
        try:
            cursor.execute('ALTER TABLE style_guide ADD COLUMN source TEXT DEFAULT "manual"')
        except: pass
        try:
            cursor.execute('ALTER TABLE style_guide ADD COLUMN quality_score REAL DEFAULT 0')
        except: pass
        try:
            cursor.execute('ALTER TABLE style_guide ADD COLUMN source_chapter INTEGER')
        except: pass

        # 卷管理表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS volumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                description TEXT,
                goal TEXT,
                status TEXT DEFAULT 'planned'
            )
        ''')

        # 单元管理表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS arcs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                volume_id INTEGER,
                name TEXT,
                description TEXT,
                goal TEXT,
                key_events JSON, 
                start_chapter INTEGER,
                end_chapter_estimated INTEGER,
                status TEXT DEFAULT 'planned',
                FOREIGN KEY(volume_id) REFERENCES volumes(id)
            )
        ''')

        # 分级摘要表 (Fractal Summaries)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS summary_aggregations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT, -- 'batch_10', 'volume', 'global'
                start_chapter INTEGER,
                end_chapter INTEGER,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 世界圣经 (World Bible) - 绝对真理库
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS world_bible (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT, -- 'WorldRule', 'Magic', 'CharacterCore', 'History'
                topic TEXT,    -- e.g. 'Mana', 'Protagonist_Vengeance', 'Kingdom_Map'
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 文风样板库 (Style Guide / Golden Samples)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS style_guide (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT, -- 'Action', 'Scenery', 'Dialogue', 'InnerMonologue'
                content TEXT,
                notes TEXT,
                -- 🔥 P2新增: 自动学习支持
                source TEXT DEFAULT 'manual', -- 'manual' | 'auto_learned'
                quality_score REAL DEFAULT 0, -- 质量评分 (0-100)
                source_chapter INTEGER, -- 来源章节
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 黄金锚点表 (Immutable Anchors) - 锁定人设核心
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS character_anchors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_name TEXT,
                category TEXT, -- 'Motivation' (源动力), 'Trauma' (创伤), 'Vow' (誓言), 'Tone' (语调)
                content TEXT,
                tags TEXT, -- JSON list of triggers e.g. ["fight", "despair"]
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 混沌冷却池 (Chaos Cooldowns)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chaos_cooldowns (
                category TEXT PRIMARY KEY,
                cooldown_until INTEGER -- 直到第几章才解冻
            )
        ''')

        # 遥测指标表 (Narrative Telemetry) - 防崩坏监控
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chapter_metrics (
                chapter_num INTEGER PRIMARY KEY,
                tension INTEGER, -- 0-100
                tone_darkness INTEGER, -- 0-100 (越高越压抑)
                pacing_score INTEGER, -- 0-100 (越高越快)
                character_consistency_score INTEGER, -- 0-100 (100为完美一致)
                plot_logic_score INTEGER, -- 0-100 (100为无漏洞)
                critique TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # --- 地理信息系统 (GIS) ---
        
        # 地点表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS locations (
                name TEXT PRIMARY KEY,
                description TEXT,
                type TEXT, -- City, Wild, Dungeon, Sect
                faction TEXT, -- 所属势力
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 路径表 (有向图)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                target TEXT,
                travel_time_days INTEGER,
                travel_methods TEXT, -- JSON: {"Walk": "desc", "Fly": "desc"}
                requirements TEXT, -- JSON: ["Level > 10", "Item:Map"]
                UNIQUE(source, target)
            )
        ''')

        # 🔥 P0新增: 关系备份表 (Neo4j Fallback)
        # 当Neo4j不可用时，使用此表存储简化的关系信息
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS relationship_backup (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_name TEXT NOT NULL,
                source_type TEXT DEFAULT 'Character',
                relation TEXT NOT NULL,
                target_name TEXT NOT NULL,
                target_type TEXT DEFAULT 'Character',
                description TEXT,
                start_chapter INTEGER,
                end_chapter INTEGER,  -- NULL表示关系仍有效
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_name, relation, target_name, start_chapter)
            )
        ''')

        # 🔥 P0新增: 事件备份表 (Neo4j Fallback)

        # Entity Ledger (Hard Logic State)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS entity_ledger (
                name TEXT PRIMARY KEY,
                type TEXT NOT NULL, -- Item, Location, Character_State
                current_state TEXT NOT NULL, -- e.g., "InInventory", "Destroyed", "Cursed"
                holder TEXT, -- Who holds the item or where the entity is
                last_updated_chapter INTEGER,
                metadata TEXT, -- JSON for extra details
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS event_backup (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_uid TEXT UNIQUE NOT NULL,
                description TEXT,
                chapter INTEGER,
                event_type TEXT DEFAULT 'Major',
                participants TEXT,  -- JSON: ["角色1", "角色2"]
                cause_event_uid TEXT,  -- 因果链: 上游事件
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 🔥 P0优化: 创建高频查询索引
        print("   📊 正在创建性能优化索引...")

        # 1. 章节查询索引 (最高频)
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_chapters_num ON chapters(chapter_num)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_events_chapter ON events(chapter_num, character_name)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_metrics_chapter ON chapter_metrics(chapter_num)
        ''')

        # 2. 角色别名查询索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_aliases_lookup ON character_aliases(alias, character_id)
        ''')

        # 3. 伏笔状态索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_foreshadowing_status ON foreshadowing(status, chapter_created)
        ''')

        # 4. 单元/卷状态索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_arcs_status ON arcs(status, volume_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_volumes_status ON volumes(status)
        ''')

        # 5. 🔥 P0新增: 关系备份索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_rel_backup_source ON relationship_backup(source_name, end_chapter)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_rel_backup_target ON relationship_backup(target_name, end_chapter)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_event_backup_chapter ON event_backup(chapter)
        ''')

        print("   ✅ 索引创建完成")

        conn.commit()
        conn.close()

    # --- Entity Ledger Methods ---

    def update_entity_state(self, name: str, entity_type: str, state: str, 
                          holder: str = None, chapter_num: int = 0, metadata: Dict = None):
        """
        🔥 P4新增: 更新实体状态账本 (The Ledger)
        用于追踪关键物品、地点状态、角色身体状态等硬逻辑。
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        import json
        meta_str = json.dumps(metadata, ensure_ascii=False) if metadata else "{}"
        
        cursor.execute('''
            INSERT OR REPLACE INTO entity_ledger 
            (name, type, current_state, holder, last_updated_chapter, metadata, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (name, entity_type, state, holder, chapter_num, meta_str))
        
        conn.commit()
        conn.close()
        print(f"   📒 Ledger Update: [{entity_type}] {name} -> {state} (Holder: {holder})")

    def get_entity_states(self, names: List[str] = None, entity_type: str = None) -> List[Dict]:
        """获取实体状态账本记录"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = "SELECT name, type, current_state, holder, last_updated_chapter, metadata FROM entity_ledger WHERE 1=1"
        params = []
        
        if names:
            placeholders = ','.join(['?'] * len(names))
            query += f" AND name IN ({placeholders})"
            params.extend(names)
            
        if entity_type:
            query += " AND type = ?"
            params.append(entity_type)
            
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        results = []
        import json
        for r in rows:
            results.append({
                "name": r[0],
                "type": r[1],
                "state": r[2],
                "holder": r[3],
                "last_updated": r[4],
                "metadata": json.loads(r[5]) if r[5] else {}
            })
        return results

    def get_full_ledger_context(self, active_characters: List[str]) -> str:
        """
        🔥 P4新增: 为Writer构建账本上下文
        1. 获取所有相关角色的身体状态
        2. 获取他们持有的重要物品
        3. 获取全局重要状态 (Global Flags)
        """
        states = []
        
        # 1. 角色相关状态 (持有物品、身体状态)
        # 查询 holder 在 active_characters 里的记录，或者 name 在 active_characters 里的记录 (自身状态)
        conn = self._get_connection()
        cursor = conn.cursor()
        
        placeholders = ','.join(['?'] * len(active_characters)) if active_characters else "''"
        
        # 参数: active_characters (for holder) + active_characters (for name)
        params = active_characters + active_characters if active_characters else []
        
        cursor.execute(f'''
            SELECT name, type, current_state, holder, metadata 
            FROM entity_ledger 
            WHERE holder IN ({placeholders}) 
               OR (name IN ({placeholders}) AND type = 'Character_State')
               OR type = 'Global_Flag'
        ''', params)
        
        rows = cursor.fetchall()
        conn.close()
        
        import json
        
        char_states = {} # key: char_name
        inventory = {}   # key: char_name
        globals = []
        
        for row in rows:
            name, etype, state, holder, meta_raw = row
            meta = json.loads(meta_raw) if meta_raw else {}
            
            desc = f"{name}: {state}"
            if meta.get("effect"):
                desc += f" ({meta['effect']})"
            
            if etype == 'Global_Flag':
                globals.append(f"⚠️ [WORLD] {desc}")
            elif etype == 'Character_State':
                owner = holder if holder else name
                if owner not in char_states: char_states[owner] = []
                char_states[owner].append(desc) 
            else: # Items, etc.
                if holder:
                    if holder not in inventory: inventory[holder] = []
                    inventory[holder].append(desc)
                    
        # 格式化输出
        lines = []
        if globals:
            lines.append("### 🌍 世界规则/状态 (Global Flags)")
            lines.extend(globals)
            
        if char_states or inventory:
            lines.append("### 🎒 实体状态账本 (Entity Ledger - Must Obey)")
            all_chars = set(char_states.keys()) | set(inventory.keys())
            for char in all_chars:
                items = inventory.get(char, [])
                states = char_states.get(char, [])
                
                segment = f"- **{char}**:"
                if states:
                    segment += f" [状态: {', '.join(states)}]"
                if items:
                    segment += f" [持有: {'; '.join(items)}]"
                lines.append(segment)
                
        return "\n".join(lines) if lines else ""

    # --- 遥测指标 (Narrative Telemetry) ---

    def _get_connection(self):
        """
        🔥 P0优化: 获取数据库连接 (带超时和优化参数)
        """
        conn = sqlite3.connect(
            self.db_path,
            timeout=self._connection_timeout,
            isolation_level=None  # 自动提交模式,减少锁竞争
        )
        # 为每个连接启用优化参数
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def log_chapter_metrics(self, chapter_num: int, metrics: Dict[str, Any]):
        """记录章节遥测数据 - 🔥 P0优化: 使用优化连接"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO chapter_metrics (chapter_num, tension, tone_darkness, pacing_score, character_consistency_score, plot_logic_score, critique)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chapter_num) DO UPDATE SET
                tension=excluded.tension,
                tone_darkness=excluded.tone_darkness,
                pacing_score=excluded.pacing_score,
                character_consistency_score=excluded.character_consistency_score,
                plot_logic_score=excluded.plot_logic_score,
                critique=excluded.critique
        ''', (
            chapter_num,
            metrics.get("tension", 50),
            metrics.get("tone_darkness", 50),
            metrics.get("pacing_score", 50),
            metrics.get("character_consistency_score", 100),
            metrics.get("plot_logic_score", 100),
            metrics.get("critique", "")
        ))
        conn.close()
        print(f"📈 Metrics Logged for Ch{chapter_num}: Tension={metrics.get('tension')}")

    def get_metrics_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近的遥测数据，用于绘制图表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT chapter_num, tension, tone_darkness, pacing_score, character_consistency_score, plot_logic_score 
            FROM chapter_metrics 
            ORDER BY chapter_num ASC
        ''') # 获取全部数据交给前端绘图通常更好，limit 可以在前端做，或者这里做
        # 如果数据量太大，再加 LIMIT。目前全部返回以便画完整曲线。
        
        columns = ["chapter", "tension", "darkness", "pacing", "char_consistency", "plot_logic"]
        data = [dict(zip(columns, row)) for row in cursor.fetchall()]
        conn.close()
        return data

    # --- 混沌冷却管理 (Chaos Cooldowns) ---

    def get_active_cooldowns(self, current_chapter: int) -> List[str]:
        """获取当前仍处于冷却中的混沌类别"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT category FROM chaos_cooldowns WHERE cooldown_until > ?', (current_chapter,))
        rows = cursor.fetchall()
        conn.close()
        return [r[0] for r in rows]

    def set_chaos_cooldown(self, category: str, current_chapter: int, duration: int):
        """设定某类混沌事件的冷却期"""
        cooldown_until = current_chapter + duration
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO chaos_cooldowns (category, cooldown_until) VALUES (?, ?)
            ON CONFLICT(category) DO UPDATE SET cooldown_until = ?
        ''', (category, cooldown_until, cooldown_until))
        conn.commit()
        conn.close()
        print(f"🧊 Chaos Category '{category}' frozen until Ch{cooldown_until}")

    # --- 黄金锚点 (Immutable Anchors) ---

    def add_anchor(self, character_name: str, category: str, content: str, tags: List[str] = None):
        """
        添加一个“黄金锚点”。这是角色绝对不能违背的设定/原文。
        用于防止长篇连载中的人设漂移。
        """
        if tags is None: tags = []
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO character_anchors (character_name, category, content, tags) 
            VALUES (?, ?, ?, ?)
        ''', (character_name, category, content, json.dumps(tags)))
        conn.commit()
        conn.close()
        print(f"⚓️ Anchor Set for {character_name}: [{category}]")

    def get_character_anchors(self, character_name: str) -> str:
        """获取角色的绝对锚点，格式化为 System Instruction"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT category, content, tags 
            FROM character_anchors 
            WHERE character_name = ? AND is_active = 1
        ''', (character_name,))
        rows = cursor.fetchall()
        conn.close()

        if not rows: return ""

        lines = [f"### ⚓️ {character_name} 的黄金锚点 (Immutable Anchors) - 必须严格遵守"]
        for cat, content, tags_json in rows:
            tags = json.loads(tags_json)
            tag_str = f" [触发: {', '.join(tags)}]" if tags else ""
            lines.append(f"- 【{cat}】{tag_str}: {content}")
        
        return "\n".join(lines)

    # --- 文风样板 (Style Guide) ---

    def add_style_sample(self, category: str, content: str, notes: str = ""):
        """添加一个黄金样板段落"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO style_guide (category, content, notes) VALUES (?, ?, ?)', (category, content, notes))
        conn.commit()
        conn.close()
        print(f"🖋️ Style Sample Added: [{category}]")

    def get_style_examples(self, tags: List[str] = None, limit: int = 3) -> str:
        """
        🔥 P2升级: 获取文风样板 (Style Guide)
        优先从自动学习的高分章节中获取，其次是手动添加的样板
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        rows = []

        # 🔥 P2新增: 优先从自动学习的样板中获取
        if tags:
            placeholders = ','.join(['?'] * len(tags))
            sql = f"""
                SELECT category, content FROM style_guide
                WHERE category IN ({placeholders}) AND source = 'auto_learned'
                ORDER BY quality_score DESC, RANDOM()
                LIMIT ?
            """
            params = list(tags) + [limit]
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        # 如果自动学习的不够，补充手动添加的
        if len(rows) < limit and tags:
            remaining = limit - len(rows)
            placeholders = ','.join(['?'] * len(tags))
            sql = f"""
                SELECT category, content FROM style_guide
                WHERE category IN ({placeholders}) AND (source IS NULL OR source = 'manual')
                ORDER BY RANDOM()
                LIMIT ?
            """
            params = list(tags) + [remaining]
            cursor.execute(sql, params)
            rows.extend(cursor.fetchall())

        # 如果没有找到，或者没提供 tags，尝试获取默认
        if not rows:
            cursor.execute("""
                SELECT category, content FROM style_guide
                WHERE category IN ('General', 'Narrative', 'Default')
                ORDER BY COALESCE(quality_score, 0) DESC, RANDOM()
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()

        conn.close()

        if not rows: return ""

        lines = ["# 🖋️ 文风参考 (Style Reference) - 请模仿以下笔触"]
        for cat, content in rows:
            lines.append(f"--- [Example: {cat}] ---\n{content}")

        return "\n".join(lines)

    def get_style_sample_list(self, tags: List[str] = None, limit: int = 5) -> List[str]:
        """
        🔥 P2配套: 获取原始文风样板列表 (供 StyleChecker 分析使用)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        rows = []
        if tags:
            placeholders = ','.join(['?'] * len(tags))
            # 优先取 auto_learned (质量更高)
            sql = f"""
                SELECT content FROM style_guide
                WHERE category IN ({placeholders})
                ORDER BY CASE WHEN source='auto_learned' THEN 1 ELSE 0 END DESC, quality_score DESC, RANDOM()
                LIMIT ?
            """
            params = list(tags) + [limit]
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        # 兜底
        if not rows:
            cursor.execute("""
                SELECT content FROM style_guide
                ORDER BY quality_score DESC, RANDOM()
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()

        conn.close()
        return [r[0] for r in rows]

    def auto_learn_style_from_chapter(self, chapter_num: int, content: str, metrics: Dict[str, Any]):
        """
        🔥 P2新增 + P5修复: 自动从高分章节学习文风样板

        触发条件 (P5 修复版):
        - 该章节的 pacing_score >= 80 且 tension >= 70 (优秀战斗)
        - 且 character_consistency_score >= 85 (🔥 必须保证不 OOC)
        """
        pacing = metrics.get('pacing_score', 0)
        tension = metrics.get('tension', 0)
        thematic = metrics.get('thematic_score', 0)
        consistency = metrics.get('character_consistency_score', 0)

        # 判断是否值得学习
        should_learn = False
        categories = []
        quality_score = 0

        # 🔥 P5修复: 增加一致性硬门槛 (Consistency Gate)
        # 即使节奏再好，如果人设崩了(OOC)，绝对不能学，否则是给系统喂毒
        if consistency < 85:
            # print(f"   🛡️ 文风学习被拦截: 一致性过低 ({consistency} < 85)，防止 OOC 污染。")
            return

        if pacing >= 80 and tension >= 70:
            should_learn = True
            categories.append('Action')
            quality_score = max(quality_score, (pacing + tension) / 2)

        if thematic >= 80:
            should_learn = True
            categories.append('InnerMonologue')
            categories.append('Philosophy')
            quality_score = max(quality_score, thematic)

        # 对话类样板要求更高的一致性
        if consistency >= 90:
            should_learn = True
            categories.append('Dialogue')
            quality_score = max(quality_score, consistency)

        if not should_learn:
            return

        print(f"   📚 自动学习: 第{chapter_num}章达到优秀标准，提取文风样板...")

        # 提取精彩段落 (选择中间偏后的段落，通常是高潮部分)
        paragraphs = content.split('\n\n')
        if len(paragraphs) < 3:
            return

        # 选择中间到后半部分的段落
        start_idx = len(paragraphs) // 3
        end_idx = min(start_idx + 3, len(paragraphs))
        selected_paragraphs = paragraphs[start_idx:end_idx]

        # 过滤太短的段落
        selected_paragraphs = [p for p in selected_paragraphs if len(p) >= 100]
        if not selected_paragraphs:
            return

        # 取最长的一个作为样板
        best_paragraph = max(selected_paragraphs, key=len)

        # 限制长度
        if len(best_paragraph) > 500:
            best_paragraph = best_paragraph[:500] + "..."

        # 存储到数据库
        conn = self._get_connection()
        cursor = conn.cursor()

        for category in categories:
            cursor.execute('''
                INSERT INTO style_guide (category, content, source, quality_score, source_chapter)
                VALUES (?, ?, 'auto_learned', ?, ?)
            ''', (category, best_paragraph, quality_score, chapter_num))

        conn.commit()
        conn.close()

        print(f"      -> 已提取 {len(categories)} 个类别的样板 (质量分: {quality_score:.1f})")

    # --- 世界圣经 (World Bible / Immutable Truths) ---

    def add_bible_entry(self, category: str, topic: str, content: str):
        """添加一条绝对真理。同时存入 SQL (用于管理) 和 VectorDB (用于检索)。"""
        # 1. SQL Storage
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO world_bible (category, topic, content) 
            VALUES (?, ?, ?)
        ''', (category, topic, content))
        entry_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # 2. Vector Storage (Strongly weighted metadata)
        # 格式化内容，强调这是规则
        full_text = f"【世界圣经/绝对规则】[{category}] {topic}: {content}"
        try:
            self.vector_store.add_documents([
                Document(
                    page_content=full_text, 
                    metadata={
                        "type": "bible_truth", 
                        "category": category, 
                        "topic": topic, 
                        "entry_id": entry_id,
                        "status": "active"
                    }
                )
            ])
        except Exception as e:
            print(f"   ⚠️ Bible Vector Write Failed (Non-fatal): {e}")

        print(f"✝️ Bible Entry Added: [{category}] {topic}")

    def get_bible_context(self, query: str, active_entities: List[str] = None) -> str:
        """
        检索相关的世界圣经条目。
        策略：
        1. 关键词硬匹配 (High Precision): 检查 active_entities 是否匹配 Bible 中的 topic。
        2. 语义检索 (High Recall): 针对 query 检索相关的规则。
        """
        if active_entities is None: active_entities = []
        
        found_entries = {} # id -> content

        # A. 关键词硬匹配 (直接查询 Topic)
        if active_entities:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            # 动态构建 SQL OR 查询
            placeholders = ','.join(['?'] * len(active_entities))
            # 模糊匹配 topic，以防 active_entity 是 "Xiao Feng" 而 topic 是 "Xiao Feng's Sword"
            # 这里简化为直接匹配 topic 包含 entity 名字
            sql = f"SELECT id, category, topic, content FROM world_bible WHERE topic IN ({placeholders})"
            cursor.execute(sql, tuple(active_entities))
            rows = cursor.fetchall()
            
            for r in rows:
                entry_text = f"[{r[1]}] {r[2]}: {r[3]}"
                found_entries[r[0]] = entry_text
            conn.close()

        # B. 语义检索 (针对当前情节 query)
        # 强制过滤 type='bible_truth'
        semantic_docs = self.vector_store.similarity_search(
            query, 
            k=5, 
            filter={"$and": [{"type": "bible_truth"}, {"status": "active"}]}
        )

        
        for doc in semantic_docs:
            eid = doc.metadata.get("entry_id")
            if eid and eid not in found_entries:
                found_entries[eid] = doc.page_content

        if not found_entries:
            return ""

        # 格式化输出
        lines = ["# ✝️ 世界圣经 (Immutable Truths - DO NOT VIOLATE)"]
        for _, content in found_entries.items():
            lines.append(f"- {content}")
        
        return "\n".join(lines)

    # --- 角色操作 (UUID Core) ---

    def _get_id_by_name(self, name: str) -> Optional[str]:
        """通过名字（或别名）查找 UUID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT character_id FROM character_aliases WHERE alias = ?', (name,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def _register_alias(self, alias: str, char_id: str, is_primary: bool = False):
        """注册别名"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO character_aliases (alias, character_id, is_primary) 
            VALUES (?, ?, ?)
            ON CONFLICT(alias) DO UPDATE SET character_id = ?, is_primary = max(is_primary, ?)
        ''', (alias, char_id, is_primary, char_id, is_primary))
        conn.commit()
        conn.close()

    def upsert_character(self, name: str, update_data: Dict[str, Any], chapter_num: int = 0):
        """智能合并角色档案 (支持 UUID 和 别名) - 200万字长篇优化版"""
        
        # 1. 解析身份
        char_id = self._get_id_by_name(name)
        
        if not char_id:
            # 新角色：生成 UUID
            char_id = str(uuid.uuid4())
            self._register_alias(name, char_id, is_primary=True)
            existing_json = None
        else:
            # 旧角色：读取旧数据
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT data FROM characters WHERE id = ?', (char_id,))
            row = cursor.fetchone()
            conn.close()
            existing_json = json.loads(row[0]) if row else None

        # 2. 合并数据
        if existing_json:
            merged_data = existing_json.copy()
            
            # --- 列表型字段处理策略 ---
            
            # A. 覆盖型 (Last Write Wins)
            # 如果提供了新的列表且非空，直接覆盖旧的。
            overwrite_keys = ["personality", "goals"]
            for key in overwrite_keys:
                if key in update_data and update_data[key]:
                    merged_data[key] = update_data[key]

            # B. 增量型 (Append/Merge)
            # dialogue_examples, aliases (别名通常只增不减), mental_ledger (账本)
            append_keys = ["dialogue_examples", "aliases", "mental_ledger"]
            for list_key in append_keys:
                old_list = merged_data.get(list_key, []) or []
                new_list = update_data.get(list_key, []) or []
                
                if list_key == "mental_ledger":
                     # 账本型：简单追加 (Archive 负责生成 Entry)
                     # 确保 new_list 里的 items 是字典 (如果是 Pydantic model dump 出来的)
                    merged_data[list_key] = old_list + new_list
                else:
                    # 集合型：去重合并
                    merged_data[list_key] = list(set(old_list + new_list))

            # C. 物品栏 (Inventory) 特殊处理: 支持结构化增减
            # 1. 获取当前物品字典 (Name -> ItemDict) 用于合并
            current_inv_list = merged_data.get("inventory", []) or []
            current_inv_map = {}
            for item in current_inv_list:
                # 兼容旧数据 (str)
                if isinstance(item, str):
                    current_inv_map[item] = {"name": item, "category": "General", "quantity": 1}
                else:
                    current_inv_map[item["name"]] = item
            
            # 2. 处理新物品 (合并或覆盖)
            new_inv_list = update_data.get("inventory", []) or []
            for item in new_inv_list:
                # 同样兼容输入可能是 str (虽然 Schema 要求对象，但为了 robust)
                if isinstance(item, str):
                    name = item
                    item_data = {"name": item, "category": "General", "quantity": 1}
                else:
                    name = item["name"]
                    item_data = item
                
                # Logic: 如果已存在，更新数量/状态；如果不存在，添加
                # 这里简单处理：直接覆盖属性，但累加数量? 
                # 暂定: 直接覆盖属性 (假设 Writer Agent 能够给出最新状态)
                current_inv_map[name] = item_data
            
            # 3. 移除物品
            removed_items = set(update_data.get("removed_items", []) or [])
            for r_name in removed_items:
                if r_name in current_inv_map:
                    del current_inv_map[r_name]
            
            merged_data["inventory"] = list(current_inv_map.values())
            
            # --- Hard Logic State Merging (Body & Effects) ---
            # 策略：按 Name 唯一键合并
            
            # Body Status
            current_body = {b["name"]: b for b in merged_data.get("body_status", [])}
            new_body = update_data.get("body_status", []) or []
            for b in new_body:
                current_body[b["name"]] = b # 直接覆盖最新状态
            merged_data["body_status"] = list(current_body.values())

            # Active Effects
            current_effects = {e["name"]: e for e in merged_data.get("active_effects", [])}
            new_effects = update_data.get("active_effects", []) or []
            for e in new_effects:
                # 如果 duration 为 0 (且原本存在)，可能意味着移除？
                # 不，通常移除应该显式。这里假设 duration=0 是无限或保持。
                # 暂定策略：直接覆盖
                current_effects[e["name"]] = e
            
            # 清理过期的 Effects (Simple Logic: Check external cleaner or duration)
            # 这里暂不处理自动过期，留给 Director/Physics 每一章结束时处理
            merged_data["active_effects"] = list(current_effects.values())

            # --- 字典型字段合并 ---
            old_rel = merged_data.get("relationships", {}) or {}
            new_rel = update_data.get("relationships", {}) or {}
            old_rel.update(new_rel)
            merged_data["relationships"] = old_rel

            # --- 心理状态特殊处理 ---
            if "psychological_state" in update_data and update_data["psychological_state"] != merged_data.get("psychological_state"):
                old_state = merged_data.get("psychological_state", "未知")
                new_state = update_data["psychological_state"]
                # 自动记录一条历史
                if not update_data.get("psychological_history"):
                     merged_data.setdefault("psychological_history", []).append({
                        "chapter": chapter_num,
                        "state": new_state,
                        "change_from": old_state,
                        "note": "State update detected"
                    })
                merged_data["psychological_state"] = new_state

            # --- 其他字段覆盖 (Level, Status, Role, Importance) ---
            # 这些字段通常是单值，直接覆盖
            exclude_keys = overwrite_keys + append_keys + ["relationships", "id", "psychological_state", "inventory", "removed_items", "body_status", "active_effects"]
            for k, v in update_data.items():
                if k not in exclude_keys and v is not None: 
                    merged_data[k] = v
        else:
            # 全新角色
            merged_data = update_data
            merged_data["id"] = char_id
            
            # 初始化列表 (防止 None)
            for k in ["aliases", "personality", "goals", "inventory", "psychological_history", "dialogue_examples", "body_status", "active_effects"]:
                if k not in merged_data or merged_data[k] is None:
                    merged_data[k] = []
                    
            if name not in merged_data["aliases"]:
                merged_data["aliases"].append(name)
            
            # 处理 Inventory/Removed logic even for new char
            if "removed_items" in merged_data:
                del merged_data["removed_items"] # 新角色没有需要移除的
            
            # Normalize Inventory to Objects if they are strings
            normalized_inv = []
            for item in merged_data["inventory"]:
                if isinstance(item, str):
                    normalized_inv.append({"name": item, "category": "General", "quantity": 1})
                else:
                    normalized_inv.append(item)
            merged_data["inventory"] = normalized_inv

        merged_data["last_updated_chapter"] = chapter_num
        merged_data["name"] = name 

        # 3. 处理别名注册
        if "aliases" in merged_data:
            for alias in merged_data["aliases"]:
                self._register_alias(alias, char_id)

        # 4. Schema 校验
        # 移除临时字段 removed_items 以免 Pydantic 报错 (如果它不在 Schema 里)
        if "removed_items" in merged_data:
            del merged_data["removed_items"]
            
        validated_data = CharacterSchema(**merged_data)
        
        # 5. 存入数据库
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO characters (id, name, data) VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET data = ?, name = ?, updated_at = CURRENT_TIMESTAMP
        ''', (char_id, name, validated_data.model_dump_json(), validated_data.model_dump_json(), name))
        conn.commit()
        conn.close()

    def get_character(self, name: str) -> Optional[Dict[str, Any]]:
        char_id = self._get_id_by_name(name)
        if not char_id: return None
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT data FROM characters WHERE id = ?', (char_id,))
        row = cursor.fetchone()
        conn.close()
        return json.loads(row[0]) if row else None

    def get_character_details(self, names: List[str], query: str = "") -> str:
        if not names: return "无在场角色详情。"
        details = []
        # 去重：先解析 UUID，避免同一个人的不同外号被查询两次
        unique_ids = set()
        for name in names:
            uid = self._get_id_by_name(name)
            if uid: unique_ids.add(uid)
        
        for uid in unique_ids:
            # 直接查 ID
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT name, data FROM characters WHERE id = ?', (uid,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                name, data_json = row
                data = json.loads(data_json)
                info = f"--- {name} (ID: {uid[:8]}) ---\n"
                for k, v in data.items():
                    if k not in ["name", "id", "aliases"]: info += f"{k}: {v}\n"
                
                # 别名展示
                aliases = data.get("aliases", [])
                if aliases: info += f"曾用名/别名: {', '.join(aliases)}\n"

                # 注入黄金锚点 (Highest Priority)
                anchors = self.get_character_anchors(name)
                if anchors:
                    info = anchors + "\n\n" + info

                history = self.get_relevant_events(name, query=query, recent_k=3, semantic_k=3)
                if history != "无相关历史事件。":
                    info += f"【关键经历】:\n{history}\n"
                details.append(info)
        return "\n".join(details) if details else "未找到指定角色档案。"

    def get_character_roster_brief(self) -> str:
        """
        全量花名册 (for Editor): 按【地点】分组展示所有存活角色，以便主编把控全局。
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT name, data FROM characters')
        rows = cursor.fetchall()
        conn.close()
        
        grouped_roster = {} # location -> [names]
        
        for name, data_json in rows:
            data = json.loads(data_json)
            # 过滤掉已死亡或极其不重要的角色 (可选)
            if data.get("current_state") == "死亡":
                continue

            loc = data.get("location", "未知")
            role = data.get("role", "NPC")
            imp = data.get("importance", "NPC")
            
            # 格式: 萧风(主角/凝气三层)
            entry = f"{name}({role})"
            
            if loc not in grouped_roster:
                grouped_roster[loc] = []
            grouped_roster[loc].append(entry)
            
        # 格式化输出
        lines = []
        for loc, chars in grouped_roster.items():
            lines.append(f"📍【{loc}】：{', '.join(chars)}")
            
        return "\n".join(lines) if lines else "暂无角色记录。"

    def get_local_roster(self, current_location: str, include_global_protagonists: bool = True) -> str:
        """
        本地花名册 (for Writer): 仅返回【当前地点】的角色 + 【全局主角】 + 【重要配角】。
        避免无关的远方角色干扰写作。
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT name, data FROM characters')
        rows = cursor.fetchall()
        conn.close()
        
        relevant_chars = []
        
        for name, data_json in rows:
            data = json.loads(data_json)
            if data.get("current_state") == "死亡": continue

            loc = data.get("location", "未知")
            imp = data.get("importance", "NPC")
            
            # 筛选逻辑：
            # 1. 在当前地点
            # 2. 或者是主角 (Protagonist)
            # 3. 或者是重要配角 (Major) - 可选，看是否希望随时能提及他们
            is_local = (loc == current_location)
            is_important = (imp in ["Protagonist", "Major"])
            
            if is_local or (include_global_protagonists and is_important):
                role_info = f"{data.get('role', '未知')}/{data.get('level', '?')}"
                
                # 获取简单的状态描述
                state = data.get("psychological_state", "平稳")
                
                relevant_chars.append(f"- {name} [{role_info}] @ {loc} (State: {state})")
                
        return "\n".join(relevant_chars) if relevant_chars else "（当前地点无其他已知角色）"

    def get_character_mental_curve(self, names: List[str], limit: int = 5) -> str:
        """
        获取角色精神心电图 (Mental Curve / Ledger Snapshot)
        用于 Simulator 和 Writer 把控情绪惯性。
        """
        if not names: return "无在场角色。"
        
        curves = []
        unique_ids = set()
        for name in names:
            uid = self._get_id_by_name(name)
            if uid: unique_ids.add(uid)
            
        for uid in unique_ids:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT name, data FROM characters WHERE id = ?', (uid,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                name, data_json = row
                data = json.loads(data_json)
                ledger = data.get("mental_ledger", [])
                
                # 取最近的记录
                recent = sorted(ledger, key=lambda x: x['chapter'])[-limit:]
                
                if not recent:
                    curves.append(f"{name}: 暂无精神记录 (Default: 平稳)")
                    continue
                    
                chart = f"📊 {name} 的精神轨迹:\n"
                for entry in recent:
                    # Visual bar for intensity
                    bar = "█" * (entry.get('intensity', 0) // 10)
                    sanity = entry.get('sanity', 100)
                    chart += f"   - Ch{entry['chapter']}: {entry['state']} {bar} (SAN: {sanity}) -> {entry['reason']}\n"
                curves.append(chart)
                
        return "\n".join(curves)

    def get_hard_logic_snapshot(self, names: List[str]) -> str:
        """
        获取硬逻辑快照 (Hard Logic Snapshot)
        用于 Reviewer 进行逻辑一致性检查。返回关键状态字段。
        """
        if not names: return "无相关实体。"
        
        snapshot = []
        unique_ids = set()
        for name in names:
            uid = self._get_id_by_name(name)
            if uid: unique_ids.add(uid)
            
        for uid in unique_ids:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT name, data FROM characters WHERE id = ?', (uid,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                name, data_json = row
                data = json.loads(data_json)
                
                # 提取硬逻辑字段
                state = data.get("current_state", "正常")
                loc = data.get("location", "未知")
                inventory = data.get("inventory", [])
                level = data.get("level", "未知")
                
                # 格式化
                info = f"--- {name} ---\n"
                info += f"状态: {state}\n"
                info += f"位置: {loc}\n"
                info += f"境界: {level}\n"
                
                # 🔥 P3修复: 处理对象型物品栏
                inv_names = []
                for item in inventory:
                    if isinstance(item, str):
                        inv_names.append(item)
                    elif isinstance(item, dict):
                        inv_names.append(item.get("name", "未知物品"))
                
                info += f"物品栏: {', '.join(inv_names) if inv_names else '空'}\n"
                snapshot.append(info)
                
        return "\n".join(snapshot) if snapshot else "无有效硬逻辑数据。"

    # --- 章节与节奏 ---

    def update_chapter_summary(self, chapter_num: int, summary: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO chapters (chapter_num) VALUES (?)', (chapter_num,))
        cursor.execute('UPDATE chapters SET summary = ? WHERE chapter_num = ?', (summary, chapter_num))
        cursor.execute('UPDATE narrative_focus SET chapters_since_last_beat = chapters_since_last_beat + 1 WHERE id = 1')
        conn.commit()
        conn.close()

    def update_chapter_info(self, chapter_num: int, title: str, summary: str):
        """Update both title and summary for a chapter"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO chapters (chapter_num) VALUES (?)', (chapter_num,))
        cursor.execute('UPDATE chapters SET title = ?, summary = ? WHERE chapter_num = ?', (title, summary, chapter_num))
        conn.commit()
        conn.close()

    def get_chapter_summary(self, chapter_num: int) -> str:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT summary FROM chapters WHERE chapter_num = ?', (chapter_num,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] else "暂无摘要。"

    def update_narrative_focus(self, volume: str, arc: str, beat: str, goal: str, conflict: str, state: str, reset_beat: bool = False, current_date: str = None, current_theme: str = None, pacing_directive: str = None, echo_count_delta: int = 0):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        update_parts = [
            "current_volume = excluded.current_volume",
            "current_arc = excluded.current_arc",
            "current_beat = excluded.current_beat",
            "current_goal = excluded.current_goal",
            "current_conflict = excluded.current_conflict",
            "world_state_summary = excluded.world_state_summary",
            "updated_at = CURRENT_TIMESTAMP"
        ]
        
        if reset_beat:
            update_parts.append("chapters_since_last_beat = 0")
        
        val_date = None
        if current_date:
            update_parts.append("current_date = excluded.current_date")
            val_date = current_date

        if current_theme:
            update_parts.append("current_theme = excluded.current_theme")

        if pacing_directive:
            update_parts.append("pacing_directive = excluded.pacing_directive")
            
        # 增量更新 echo_count
        if echo_count_delta != 0:
            pass 

        set_clause = ", ".join(update_parts)
        
        # 默认值
        def_theme = current_theme if current_theme else "成长"
        def_pacing = pacing_directive if pacing_directive else "Normal"
        
        # 基础 UPSERT
        insert_sql = '''
            INSERT INTO narrative_focus (id, current_volume, current_arc, current_beat, current_goal, current_conflict, world_state_summary, chapters_since_last_beat, current_date, current_theme, pacing_directive, thematic_echo_count, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, 0, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                {set_clause}
        '''
        
        # 参数准备
        params = [volume, arc, beat, goal, conflict, state, val_date, def_theme, def_pacing]
        
        # 渲染 set_clause
        final_sql = insert_sql.format(set_clause=set_clause)
        
        cursor.execute(final_sql, params)
        
        # 独立执行 Echo Count 的增量更新
        if echo_count_delta != 0:
            cursor.execute('UPDATE narrative_focus SET thematic_echo_count = thematic_echo_count + ? WHERE id = 1', (echo_count_delta,))

        conn.commit()
        conn.close()
    
    def update_world_date(self, new_date: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('UPDATE narrative_focus SET current_date = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1', (new_date,))
        if cursor.rowcount == 0:
             cursor.execute('''
                INSERT INTO narrative_focus (id, current_volume, current_arc, current_beat, current_goal, current_conflict, world_state_summary, chapters_since_last_beat, current_date, updated_at)
                VALUES (1, '序章', '未开始', '无', '无', '无', '无', 0, ?, CURRENT_TIMESTAMP)
            ''', (new_date,))
        conn.commit()
        conn.close()

    def get_narrative_focus(self) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT current_volume, current_arc, current_beat, current_goal, current_conflict, world_state_summary, chapters_since_last_beat, current_date, current_theme, pacing_directive, thematic_echo_count FROM narrative_focus WHERE id = 1')
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "volume": row[0], 
                "arc": row[1], 
                "beat": row[2], 
                "goal": row[3], 
                "conflict": row[4], 
                "state": row[5], 
                "chapters_since_last_beat": row[6],
                "date": row[7],
                "theme": row[8] if len(row) > 8 else "成长",
                "pacing": row[9] if len(row) > 9 else "Normal",
                "echo_count": row[10] if len(row) > 10 else 0
            }
        return {
            "volume": "序章", "arc": "引导篇", "beat": "背景铺垫", "goal": "确立主角身份",
            "conflict": "生存危机", "state": "一切尚未开始。",
            "chapters_since_last_beat": 0,
            "date": "天道历元年1月1日",
            "theme": "生存",
            "pacing": "Normal",
            "echo_count": 0,
            "last_echo_chapter": 0,
            "arc_start_chapter": 1
        }

    def get_effective_echo_count(self, current_chapter: int) -> float:
        """
        🔥 P2新增: 获取带衰减的母题回响有效值

        衰减公式:
        - 每隔5章未回响，有效值衰减10%
        - 最低衰减到原始值的30%

        Returns:
            有效的回响计数 (可能是小数)
        """
        focus = self.get_narrative_focus()
        raw_count = focus.get('echo_count', 0)
        last_echo = focus.get('last_echo_chapter', 0)

        if raw_count == 0:
            return 0

        chapters_since_echo = current_chapter - last_echo
        decay_periods = chapters_since_echo // 5

        # 衰减率: 每期衰减10%, 最低30%
        decay_factor = max(0.3, 1.0 - (decay_periods * 0.1))
        effective_count = raw_count * decay_factor

        return effective_count

    def record_thematic_echo(self, chapter_num: int, echo_strength: int = 1):
        """
        🔥 P2新增: 记录一次母题回响

        Args:
            chapter_num: 当前章节
            echo_strength: 回响强度 (1=普通, 2=强烈, 3=高潮点题)
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE narrative_focus
            SET thematic_echo_count = thematic_echo_count + ?,
                last_echo_chapter = ?
            WHERE id = 1
        ''', (echo_strength, chapter_num))

        conn.commit()
        conn.close()
        print(f"   ✨ 母题回响记录: 强度{echo_strength}, 章节{chapter_num}")

    def reset_echo_for_new_arc(self, arc_name: str, chapter_num: int, new_theme: str = None):
        """
        🔥 P2新增: 切换单元时重置母题计数

        当开始新的叙事单元(Arc)时:
        1. 重置echo_count为0
        2. 更新arc_start_chapter
        3. 可选更新主题
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        update_fields = [
            "thematic_echo_count = 0",
            "last_echo_chapter = ?",
            "arc_start_chapter = ?",
            "current_arc = ?"
        ]
        params = [chapter_num, chapter_num, arc_name]

        if new_theme:
            update_fields.append("current_theme = ?")
            params.append(new_theme)

        sql = f"UPDATE narrative_focus SET {', '.join(update_fields)} WHERE id = 1"
        cursor.execute(sql, params)

        conn.commit()
        conn.close()
        print(f"   🔄 单元切换: {arc_name}, 母题计数重置, 起始章节: {chapter_num}")
        if new_theme:
            print(f"      新母题: {new_theme}")

    def check_thematic_health(self, current_chapter: int) -> Dict[str, Any]:
        """
        🔥 P2新增: 检查母题健康度

        Returns:
            Dict with:
            - effective_echo: 有效回响值
            - chapters_since_last: 距上次回响章节数
            - health_status: 'healthy' | 'warning' | 'critical'
            - recommendation: 建议操作
        """
        focus = self.get_narrative_focus()
        effective_echo = self.get_effective_echo_count(current_chapter)
        last_echo = focus.get('last_echo_chapter', 0)
        arc_start = focus.get('arc_start_chapter', 1)

        chapters_since_last = current_chapter - last_echo
        chapters_in_arc = current_chapter - arc_start

        # 健康度判断
        # 每20章应该至少有3次回响 (目标echo_count >= 3)
        expected_echoes = max(1, chapters_in_arc // 20) * 3

        if effective_echo >= expected_echoes:
            status = 'healthy'
            recommendation = None
        elif effective_echo >= expected_echoes * 0.5:
            status = 'warning'
            recommendation = f"母题回响偏少，建议在近期章节中安排点题事件"
        else:
            status = 'critical'
            recommendation = f"母题严重缺失！必须在下一章安排强力点题事件"

        # 额外检查: 连续10章无回响也是危险信号
        if chapters_since_last >= 10 and status != 'critical':
            status = 'warning'
            recommendation = f"已连续{chapters_since_last}章无母题回响，建议尽快安排点题"

        return {
            "effective_echo": round(effective_echo, 2),
            "raw_echo": focus.get('echo_count', 0),
            "chapters_since_last": chapters_since_last,
            "chapters_in_arc": chapters_in_arc,
            "health_status": status,
            "recommendation": recommendation,
            "current_theme": focus.get('theme', '成长')
        }

    # --- 分级摘要管理 (Fractal Summaries) ---

    def save_aggregated_summary(self, level: str, start_chapter: int, end_chapter: int, content: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO summary_aggregations (level, start_chapter, end_chapter, content)
            VALUES (?, ?, ?, ?)
        ''', (level, start_chapter, end_chapter, content))
        conn.commit()
        conn.close()

    def get_aggregated_summaries(self, level: str, limit: int = 10) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT start_chapter, end_chapter, content 
            FROM summary_aggregations 
            WHERE level = ? 
            ORDER BY start_chapter ASC
        ''', (level,)) # 获取所有历史摘要，按时间顺序
        rows = cursor.fetchall()
        conn.close()
        # 如果 limit 限制，通常是取最近的？不，对于 Context 来说，可能需要全部 Volume 摘要
        # 这里返回全部，由调用者裁剪
        return [{"start": r[0], "end": r[1], "content": r[2]} for r in rows]

    def get_recent_aggregated_summaries(self, level: str = "batch_10", limit: int = 3) -> str:
        """获取最近的聚合摘要，用于构建中期记忆"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT start_chapter, end_chapter, content 
            FROM summary_aggregations 
            WHERE level = ? 
            ORDER BY end_chapter DESC 
            LIMIT ?
        ''', (level, limit))
        rows = cursor.fetchall()
        conn.close()
        
        if not rows: return ""
        
        # 按时间正序排列
        rows.reverse()
        
        lines = []
        for r in rows:
            lines.append(f"• [Ch{r[0]}-{r[1]} 综述]: {r[2]}")
            
        return "\n".join(lines)

    # --- 规划管理 (分级大纲) ---

    def create_volume(self, name: str, description: str, goal: str) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO volumes (name, description, goal, status) 
            VALUES (?, ?, ?, ?)
        ''', (name, description, goal, ArcStatus.PLANNED.value))
        vol_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return vol_id

    def create_arc(self, volume_id: int, name: str, description: str, goal: str, key_events: List[str], start_chapter: int = None) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO arcs (volume_id, name, description, goal, key_events, start_chapter, status) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (volume_id, name, description, goal, json.dumps(key_events), start_chapter, ArcStatus.PLANNED.value))
        arc_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return arc_id

    def activate_arc(self, arc_id: int, start_chapter: int):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # 1. 激活新 Arc
        cursor.execute('UPDATE arcs SET status = ?, start_chapter = ? WHERE id = ?', (ArcStatus.ACTIVE.value, start_chapter, arc_id))
        
        # 2. 同时激活对应的 Volume (如果还没激活)
        cursor.execute('SELECT volume_id FROM arcs WHERE id = ?', (arc_id,))
        row = cursor.fetchone()
        if row:
            vol_id = row[0]
            cursor.execute('UPDATE volumes SET status = ? WHERE id = ? AND status = ?', (ArcStatus.ACTIVE.value, vol_id, ArcStatus.PLANNED.value))
            
        conn.commit()
        conn.close()

    def get_active_plan(self) -> Dict[str, Any]:
        """获取当前激活的 Volume 和 Arc 详情"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        plan = {"volume": None, "arc": None}
        
        # 查找 Active Volume
        cursor.execute('SELECT id, name, description, goal FROM volumes WHERE status = ? LIMIT 1', (ArcStatus.ACTIVE.value,))
        vol_row = cursor.fetchone()
        if vol_row:
            plan["volume"] = {
                "id": vol_row[0],
                "name": vol_row[1],
                "description": vol_row[2],
                "goal": vol_row[3]
            }
            
            # 查找 Active Arc under this volume
            cursor.execute('SELECT id, name, description, goal, key_events, start_chapter FROM arcs WHERE volume_id = ? AND status = ? LIMIT 1', (vol_row[0], ArcStatus.ACTIVE.value))
            arc_row = cursor.fetchone()
            if arc_row:
                 plan["arc"] = {
                    "id": arc_row[0],
                    "name": arc_row[1],
                    "description": arc_row[2],
                    "goal": arc_row[3],
                    "key_events": json.loads(arc_row[4]),
                    "start_chapter": arc_row[5]
                }
        
        conn.close()
        return plan

    def complete_arc(self, arc_id: int, end_chapter: int):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('UPDATE arcs SET status = ?, end_chapter_estimated = ? WHERE id = ?', (ArcStatus.COMPLETED.value, end_chapter, arc_id))
        conn.commit()
        conn.close()

    # --- 事件与伏笔 (支持 RealityLayer) ---

    def log_event(self, chapter_num: int, character_name: str, event_type: str, description: str, layer: str = "Reality", cause_event_id: int = None):
        """
        记录事件。
        增强: 同步写入 Knowledge Graph (Event Node).
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO events (chapter_num, character_name, event_type, description, layer) VALUES (?, ?, ?, ?, ?)', 
                       (chapter_num, character_name, event_type, description, layer))
        event_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        full_text = f"[{layer}] {character_name} {event_type}: {description}"
        try:
            self.event_store.add_documents([Document(page_content=full_text, metadata={"event_id": event_id, "chapter": chapter_num, "character": character_name, "type": event_type, "layer": layer, "status": "active"})])
        except Exception as e:
            print(f"   ⚠️ Event Vector Write Failed (Non-fatal): {e}")

        # --- Graph Synchronization ---
        # 仅同步 Reality 层的事件进图谱，避免臆想污染因果链
        if layer == "Reality":
            # 1. 创建事件节点
            self.graph.add_event_node(
                event_uid=str(event_id),
                description=description,
                chapter=chapter_num,
                event_type=event_type
            )
            
            # 2. 关联参与者 (Character -> Event)
            # 如果涉及多个角色(逗号分隔)，简单处理一下
            chars = [c.strip() for c in character_name.split(',')]
            for c in chars:
                self.graph.add_participation(c, str(event_id), role="Participant")

            # 3. 如果提供了原因 (Cause)，建立因果链
            if cause_event_id:
                self.graph.add_causality(str(cause_event_id), str(event_id), reason="Explicit Link")
        
        return event_id

    def link_event_causality(self, cause_event_id: int, effect_event_id: int, reason: str = ""):
        """显式建立两个事件的因果关系"""
        self.graph.add_causality(str(cause_event_id), str(effect_event_id), reason)

    def get_relevant_events(self, character_name: str, query: str = "", recent_k: int = 5, semantic_k: int = 5) -> str:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        candidates = {}
        # 只检索真实发生的事件 (Reality)
        cursor.execute("SELECT id, chapter_num, description, event_type, layer FROM events WHERE character_name = ? AND layer = 'Reality' ORDER BY chapter_num DESC LIMIT ?", (character_name, recent_k))
        for row in cursor.fetchall():
            candidates[row[0]] = {"chapter": row[1], "desc": row[2], "type": row[3], "layer": row[4], "source": "Recent"}
        
        if query:
            # 向量检索
            results = self.event_store.similarity_search(query, k=semantic_k, filter={"character": character_name})
            for doc in results:
                evt_id = doc.metadata.get("event_id")
                layer = doc.metadata.get("layer", "Reality")
                # 可以在这里决定是否过滤非 Reality，目前保留但标注
                if evt_id and evt_id not in candidates:
                    candidates[evt_id] = {"chapter": doc.metadata.get("chapter"), "desc": doc.page_content.split(": ", 1)[-1], "type": doc.metadata.get("type"), "source": "Related", "layer": layer}
        conn.close()
        
        if not candidates: return "无相关历史事件。"
        sorted_events = sorted(candidates.values(), key=lambda x: x["chapter"])
        
        result_lines = []
        for e in sorted_events:
            prefix = "⚡️" if e['source'] == 'Related' else "🕒"
            layer_tag = f"[{e['layer']}] " if e.get('layer') != 'Reality' else ""
            result_lines.append(f"[{prefix} 第{e['chapter']}章] {layer_tag}{e['desc']}")
            
        return "\n".join(result_lines)

    def add_foreshadowing(self, chapter_num: int, content: str, importance: int = 5, tags: List[str] = None):
        if tags is None: tags = []
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 简单的 Migration Check (开发环境用)
        try:
            cursor.execute('ALTER TABLE foreshadowing ADD COLUMN importance INTEGER DEFAULT 5')
        except: pass
        try:
            cursor.execute('ALTER TABLE foreshadowing ADD COLUMN tags TEXT')
        except: pass
            
        cursor.execute('INSERT INTO foreshadowing (chapter_created, content, importance, tags) VALUES (?, ?, ?, ?)', 
                       (chapter_num, content, importance, json.dumps(tags)))
        conn.commit()
        conn.close()

    def resolve_foreshadowing(self, clue_id: int, chapter_resolved: int, confidence: float = 1.0):
        """
        🔥 P0升级: 核心伏笔(importance≥8)进入人工确认队列，而非直接回收

        Args:
            clue_id: 伏笔ID
            chapter_resolved: 提议回收的章节
            confidence: 系统检测的置信度 (0-1)
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # 检查伏笔的importance
        cursor.execute('SELECT importance, content FROM foreshadowing WHERE id = ?', (clue_id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return

        importance = row[0] or 5
        content = row[1]

        if importance >= 8:
            # 核心伏笔: 进入人工确认队列
            cursor.execute('''
                UPDATE foreshadowing
                SET pending_resolution = 1,
                    resolution_chapter_proposed = ?,
                    resolution_confidence = ?,
                    human_reviewed = 0
                WHERE id = ?
            ''', (chapter_resolved, confidence, clue_id))
            print(f"   ⏳ 核心伏笔 ID:{clue_id} 进入人工确认队列 (Importance:{importance})")
            print(f"      内容: {content[:40]}...")
        else:
            # 普通伏笔: 直接回收
            cursor.execute('''
                UPDATE foreshadowing
                SET status = "resolved",
                    chapter_resolved = ?,
                    human_reviewed = 1,
                    human_approved = 1
                WHERE id = ?
            ''', (chapter_resolved, clue_id))

        conn.commit()
        conn.close()

    def get_pending_foreshadowing_resolutions(self) -> List[Dict[str, Any]]:
        """
        🔥 P0新增: 获取待人工确认的伏笔回收列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, chapter_created, content, importance, resolution_chapter_proposed, resolution_confidence
            FROM foreshadowing
            WHERE pending_resolution = 1 AND human_reviewed = 0
            ORDER BY importance DESC, resolution_confidence DESC
        ''')
        rows = cursor.fetchall()
        conn.close()

        return [{
            "id": r[0],
            "chapter_created": r[1],
            "content": r[2],
            "importance": r[3],
            "proposed_chapter": r[4],
            "confidence": r[5]
        } for r in rows]

    def approve_foreshadowing_resolution(self, clue_id: int, approved: bool, notes: str = ""):
        """
        🔥 P0新增: 人工审核伏笔回收
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        if approved:
            # 确认回收
            cursor.execute('''
                UPDATE foreshadowing
                SET status = "resolved",
                    chapter_resolved = resolution_chapter_proposed,
                    pending_resolution = 0,
                    human_reviewed = 1,
                    human_approved = 1,
                    notes = COALESCE(notes, '') || ' | 人工确认: ' || ?
                WHERE id = ?
            ''', (notes, clue_id))
            print(f"   ✅ 伏笔 ID:{clue_id} 人工确认回收")
        else:
            # 驳回回收
            cursor.execute('''
                UPDATE foreshadowing
                SET pending_resolution = 0,
                    human_reviewed = 1,
                    human_approved = 0,
                    notes = COALESCE(notes, '') || ' | 人工驳回: ' || ?
                WHERE id = ?
            ''', (notes, clue_id))
            print(f"   ❌ 伏笔 ID:{clue_id} 人工驳回回收，保持活跃")

        conn.commit()
        conn.close()

    def get_active_foreshadowing(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # 🔥 P0修改: 排除待确认的伏笔
        cursor.execute('SELECT id, chapter_created, content, importance FROM foreshadowing WHERE status = "active" AND pending_resolution = 0 ORDER BY importance DESC')
        rows = cursor.fetchall()
        conn.close()
        return [{"id": r[0], "chapter": r[1], "content": r[2], "importance": r[3]} for r in rows]

    # --- 高光时刻管理 (Emotional Highlights) ---

    def save_highlight(self, chapter_num: int, content: str, tags: List[str] = None, sentiment: str = "Neutral"):
        """
        🔥 P5新增: 保存高光时刻 (The Emotional Rescue)
        存入原文片段，而非摘要。
        """
        if not content or len(content) < 10: return
        
        metadata = {
            "chapter": chapter_num,
            "tags": ",".join(tags) if tags else "",
            "sentiment": sentiment,
            "type": "highlight"
        }
        
        try:
            self.highlight_store.add_documents([
                Document(page_content=content, metadata=metadata)
            ])
            print(f"   ✨ Saved Highlight (Ch{chapter_num}): {content[:30]}...")
        except Exception as e:
            print(f"   ⚠️ Failed to save highlight: {e}")

    def retrieve_highlights(self, query: str, k: int = 3) -> str:
        """
        🔥 P5新增: 检索高光时刻 (用于 Context 注入)
        """
        try:
            results = self.highlight_store.similarity_search(query, k=k)
            if not results: return ""
            
            lines = ["# 🎞️ 闪回记忆 (Emotional Flashbacks - Use These Phrases!)"]
            for doc in results:
                chap = doc.metadata.get("chapter", "?")
                lines.append(f"- [Ch{chap}]: \"{doc.page_content}\"")
            
            return "\n".join(lines)
        except Exception as e:
            print(f"   ⚠️ Failed to retrieve highlights: {e}")
            return ""

    # --- 地理信息管理 (GIS) ---

    def add_location(self, name: str, description: str, loc_type: str = "Unknown", faction: str = "None"):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO locations (name, description, type, faction) VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET description=excluded.description, type=excluded.type, faction=excluded.faction
        ''', (name, description, loc_type, faction))
        conn.commit()
        conn.close()

    def add_route(self, source: str, target: str, days: int, methods: Dict[str, str], requirements: List[str] = None):
        if requirements is None: requirements = []
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO routes (source, target, travel_time_days, travel_methods, requirements) 
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source, target) DO UPDATE SET 
                travel_time_days=excluded.travel_time_days, 
                travel_methods=excluded.travel_methods,
                requirements=excluded.requirements
        ''', (source, target, days, json.dumps(methods), json.dumps(requirements)))
        conn.commit()
        conn.close()

    def get_location_info(self, name: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT name, description, type, faction FROM locations WHERE name = ?', (name,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"name": row[0], "description": row[1], "type": row[2], "faction": row[3]}
        return None

    def get_outbound_routes(self, source: str) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT target, travel_time_days, travel_methods, requirements FROM routes WHERE source = ?', (source,))
        rows = cursor.fetchall()
        conn.close()
        results = []
        for r in rows:
            results.append({
                "target": r[0],
                "days": r[1],
                "methods": json.loads(r[2]),
                "requirements": json.loads(r[3])
            })
        return results

    # --- 向量存储与混合检索 ---

    def add_chapter_context(self, text: str, chapter_num: int, metadata: Dict[str, Any] = None):
        if metadata is None: metadata = {}
        metadata.update({"chapter": chapter_num, "type": "chapter_content", "status": "active"})
        self.vector_store.add_documents([Document(page_content=text, metadata=metadata)])

    def _extract_entities_semantically(self, text: str) -> List[str]:
        """
        使用 LLM 从文本中提取关键实体 (Semantic Entity Extraction).
        替代旧的正则匹配逻辑，以解决歧义和召回率问题。
        """
        try:
            # 1. Call LLM
            # print(f"🔍 Extracting entities from: {text[:50]}...")
            json_str = self.extractor_chain.invoke({"text": text})
            
            # 2. Clean & Parse JSON
            # Basic cleaning for potential markdown fences
            json_str = json_str.replace("```json", "").replace("```", "").strip()
            
            # Attempt to find list bracket if extra text exists
            if "[" in json_str and "]" in json_str:
                start = json_str.find("[")
                end = json_str.rfind("]") + 1
                json_str = json_str[start:end]

            entities = json.loads(json_str)
            
            if isinstance(entities, list):
                # print(f"   -> Found: {entities}")
                return [str(e) for e in entities]
            return []
        except Exception as e:
            print(f"⚠️ Entity Extraction Failed: {e}")
            return []

    def archive_entity_memory(self, entity_name: str, reason: str = "Dead"):
        """
        [墓地机制] 将指定实体的相关记忆归档。
        1. SQL: 更新角色状态为 'Dead' (或传入的 reason)。
        2. VectorDB: 查找所有关联该角色的 Document，更新 metadata['status'] = 'archived'。
        """
        print(f"🪦 Archiving memories for: {entity_name} ({reason})...")
        
        # 1. Update SQL Status
        char_id = self._get_id_by_name(entity_name)
        if char_id:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            # 读取旧数据
            cursor.execute('SELECT data FROM characters WHERE id = ?', (char_id,))
            row = cursor.fetchone()
            if row:
                data = json.loads(row[0])
                data["current_state"] = reason # e.g. "Dead", "Missing", "Sealed"
                data["is_active"] = False
                
                cursor.execute('UPDATE characters SET data = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', 
                               (json.dumps(data), char_id))
                conn.commit()
                print(f"   -> SQL Status updated to '{reason}'")
            conn.close()
        else:
            print(f"   ⚠️ Character '{entity_name}' not found in SQL.")

        # 2. Update Vector Metadata (The "Ghost" Fix)
        # Chroma 的 update 需要 ids。所以必须先 query 获取 ids。
        try:
            # 获取 collection 对象 (hacky way to access underlying chroma collection)
            collection = self.vector_store._collection
            
            # 查找所有 metadata 中 character == entity_name 的记录
            # 注意：Chroma 的 where 只能精确匹配。如果 metadata["character"] 是列表或包含多个人，这里可能漏网。
            # 目前系统存储时 metadata["character"] 通常是主要角色名。
            results = collection.get(where={"character": entity_name})
            
            ids_to_update = results['ids']
            if ids_to_update:
                print(f"   -> Found {len(ids_to_update)} vector memories. Applying 'archived' tag...")
                
                # 准备新的 metadata (保留旧的，更新 status)
                # Chroma 的 update(ids=..., metadatas=...) 会覆盖 metadata。所以我们需要先读取旧的合并。
                # 但这里简化处理：假设我们需要的就是打上 archived 标签。
                # 为了安全，我们只更新 status 字段，保留其他字段有点麻烦，因为 collection.update 需要全量 metadata。
                # 更好的做法是：read -> merge -> update。
                
                current_metadatas = results['metadatas']
                new_metadatas = []
                for meta in current_metadatas:
                    new_meta = meta.copy()
                    new_meta["status"] = "archived"
                    new_metadatas.append(new_meta)
                
                collection.update(ids=ids_to_update, metadatas=new_metadatas)
                print("   ✅ Vector Archive Complete.")
            else:
                print("   -> No vector memories found to archive.")
                
        except Exception as e:
            print(f"   ⚠️ Vector Archive Failed: {e}")

    def query_related_context(self, query: str, k: int = 5, current_chapter: int = None, include_archived: bool = False) -> str:
        """
        🔥 P0优化版 + P6修复: 分区混合检索 (Partitioned Hybrid Retrieval)

        修复说明:
        - 移除了旧的 500 章硬窗口限制，解决了长程记忆断裂问题。
        - 采用 "近期热区(Recent)" + "全局高优(Global)" 双轨检索策略。
        - 确保早期的伏笔和核心设定(即使在1000章以前)也能被召回。
        """
        final_docs = {} # id/content_key -> Document

        # --- 配置参数 ---
        recent_window_size = 200  # 近期热区窗口 (章)
        recent_k = k              # 近期检索数量
        global_k = max(5, k)      # 全局检索数量 (保持较高召回)

        # 基础过滤
        base_filter = {}
        if not include_archived:
            base_filter = {"status": "active"}

        # --- Track 1: 近期热区检索 (High Precision) ---
        # 目标: 获取最近发生的、细节丰富的情节
        try:
            recent_results = []
            # 如果有章节限制，进行软过滤 (因为 Chroma 不支持复杂范围 Filter，这里做两步走)
            # 策略: 检索更多，然后 Python 过滤
            
            # 构造 Filter: 必须是 Active
            recent_search_kwargs = {"filter": base_filter} if base_filter else {}
            
            raw_recent = self.vector_store.similarity_search_with_relevance_scores(
                query, k=recent_k * 3, **recent_search_kwargs
            )

            if current_chapter is not None:
                min_chap = max(1, current_chapter - recent_window_size)
                for doc, score in raw_recent:
                    doc_chap = doc.metadata.get("chapter")
                    # 保留: 1) 无章节(通用设定) 2) 在近期窗口内
                    if doc_chap is None or (self._try_parse_int(doc_chap) >= min_chap):
                        recent_results.append((doc, score))
                        if len(recent_results) >= recent_k:
                            break
            else:
                recent_results = raw_recent[:recent_k]
                
            # 标记来源
            for doc, score in recent_results:
                doc.metadata["retrieval_source"] = "Recent"
                doc.metadata["raw_score"] = score
                self._add_to_final(final_docs, doc, score)

        except Exception as e:
            print(f"   ⚠️ 近期检索失败: {e}")

        # --- Track 2: 全局高优检索 (High Recall / Long-term Memory) ---
        # 目标: 召回早期的伏笔、核心设定、世界圣经
        # 策略: 不限制章节，但可能通过 Metadata 偏向重要内容
        try:
            # 这里的 Filter 应该更宽泛，或者针对 'type' 进行过滤? 
            # 实际上，全文检索通常能找到最好的。我们主要依靠 Score 和 Importance 加权。
            
            global_search_kwargs = {"filter": base_filter} if base_filter else {}
            
            raw_global = self.vector_store.similarity_search_with_relevance_scores(
                query, k=global_k, **global_search_kwargs
            )

            for doc, score in raw_global:
                # 过滤: 如果已经在 Recent 中找到，跳过 (由 _add_to_final 处理)
                # 加权: 如果是 Bible 或 High Importance，分数加成
                
                doc_type = doc.metadata.get("type", "unknown")
                importance = doc.metadata.get("importance", 5)
                
                boost = 1.0
                if doc_type in ["bible_truth", "world_setting", "character_core"]:
                    boost = 1.2  # 圣经/设定加权
                elif importance >= 8:
                    boost = 1.15 # 核心伏笔加权

                final_score = score * boost
                
                doc.metadata["retrieval_source"] = "Global"
                doc.metadata["raw_score"] = score
                self._add_to_final(final_docs, doc, final_score)

        except Exception as e:
            print(f"   ⚠️ 全局检索失败: {e}")

        # --- Track 3: 实体关联伏笔 (Entity Hooks) ---
        # 显式查找相关实体的未回收伏笔
        keywords = self._extract_entities_semantically(query)
        if keywords:
            active_hooks = self.get_active_foreshadowing()
            for hook in active_hooks:
                # 简单匹配: 伏笔内容包含 query 关键词
                for kw in keywords:
                    if kw in hook['content']:
                        doc = Document(
                            page_content=f"【未回收伏笔】(ID:{hook['id']}) {hook['content']}",
                            metadata={
                                "chapter": hook['chapter'], 
                                "type": "foreshadowing", 
                                "retrieval_source": "HookMatch",
                                "importance": hook['importance']
                            }
                        )
                        # 伏笔给予极高分数，确保置顶
                        self._add_to_final(final_docs, doc, 2.0)

        # --- 结果整合 ---
        # 排序: 分数降序
        sorted_docs = sorted(
            final_docs.values(), 
            key=lambda x: -x.metadata.get("final_score", 0)
        )
        
        # 截断
        sorted_docs = sorted_docs[:k]

        if not sorted_docs: return "暂无相关记忆。"

        lines = []
        for i, doc in enumerate(sorted_docs):
            source = doc.metadata.get("retrieval_source", "?")
            chapter = doc.metadata.get("chapter", "?")
            tag_map = {"Recent": "⚡️", "Global": "🌍", "HookMatch": "🔗"}
            tag = tag_map.get(source, "📄")
            
            # debug_info = f" (S:{doc.metadata.get('final_score', 0):.2f})"
            lines.append(f"--- 记忆片段 {i+1} [{tag} 第 {chapter} 章] ---\n{doc.page_content}\n")
            
        return "\n".join(lines)

    def _add_to_final(self, final_docs: Dict, doc: Document, score: float):
        """辅助函数: 去重并保留高分版本"""
        # 使用内容前50字符作为去重Key
        key = doc.page_content[:50]
        
        doc.metadata["final_score"] = score
        
        if key not in final_docs:
            final_docs[key] = doc
        else:
            # 如果已存在，保留分数高的那个
            if score > final_docs[key].metadata["final_score"]:
                final_docs[key] = doc

    def _try_parse_int(self, value):
        try:
            return int(value)
        except:
            return -1

    def similarity_search(self, query: str, k: int = 3) -> List[Document]:
        return self.vector_store.similarity_search(query, k=k)

    # --- 知识图谱 ---

    def get_social_graph(self, character_name: str, current_chapter: int = 999999) -> str:
        if not self.graph.is_connected():
            return "（知识图谱未连接，仅依赖文本记忆）"
        # 转换名字为 UUID 也许更好，但 Neo4j 节点目前还是存的名字。
        # 为了兼容性，我们还是传名字。如果需要严谨，Neo4j 节点属性也应该有 ID。
        return self.graph.query_entity_context(character_name, current_chapter=current_chapter)

    def get_visual_graph_data(self) -> Dict[str, Any]:
        return self.graph.get_visualization_data()

    def get_all_characters_list(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT name, data FROM characters')
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for name, data_json in rows:
            data = json.loads(data_json)
            result.append({
                "name": name,
                "role": data.get("role", "未知"),
                "status": data.get("current_state", "正常")
            })
        return result

    # ========================
    # 🔥 P0新增: Neo4j 降级备份系统 (Relationship Backup System)
    # ========================

    def backup_relationship(self, source: str, source_type: str, relation: str,
                           target: str, target_type: str, chapter_num: int,
                           description: str = "", is_negated: bool = False):
        """
        将关系同时写入SQLite备份表。
        当Neo4j不可用时，可从此表恢复或查询关系。
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        if is_negated:
            # 逻辑删除: 设置 end_chapter
            cursor.execute('''
                UPDATE relationship_backup
                SET end_chapter = ?, updated_at = CURRENT_TIMESTAMP
                WHERE source_name = ? AND relation = ? AND target_name = ? AND end_chapter IS NULL
            ''', (chapter_num, source, relation, target))
        else:
            # 插入或更新
            cursor.execute('''
                INSERT INTO relationship_backup (source_name, source_type, relation, target_name, target_type, description, start_chapter)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_name, relation, target_name, start_chapter) DO UPDATE SET
                    description = excluded.description,
                    updated_at = CURRENT_TIMESTAMP
            ''', (source, source_type, relation, target, target_type, description, chapter_num))

        conn.commit()
        conn.close()

    def backup_event(self, event_uid: str, description: str, chapter: int,
                    event_type: str = "Major", participants: List[str] = None,
                    cause_event_uid: str = None):
        """
        将事件同时写入SQLite备份表。
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        participants_json = json.dumps(participants or [])

        cursor.execute('''
            INSERT INTO event_backup (event_uid, description, chapter, event_type, participants, cause_event_uid)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_uid) DO UPDATE SET
                description = excluded.description,
                participants = excluded.participants,
                cause_event_uid = excluded.cause_event_uid
        ''', (event_uid, description, chapter, event_type, participants_json, cause_event_uid))

        conn.commit()
        conn.close()

    def query_relationships_from_backup(self, entity_name: str, current_chapter: int = 999999) -> str:
        """
        🔥 从SQLite备份表查询关系 (Neo4j降级模式专用)

        Returns:
            格式化的关系字符串
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # 查询该实体作为source的关系
        cursor.execute('''
            SELECT source_name, relation, target_name, target_type, description, start_chapter
            FROM relationship_backup
            WHERE source_name = ?
              AND (start_chapter IS NULL OR start_chapter <= ?)
              AND (end_chapter IS NULL OR end_chapter > ?)
            ORDER BY start_chapter DESC
            LIMIT 20
        ''', (entity_name, current_chapter, current_chapter))
        outgoing = cursor.fetchall()

        # 查询该实体作为target的关系
        cursor.execute('''
            SELECT source_name, relation, target_name, source_type, description, start_chapter
            FROM relationship_backup
            WHERE target_name = ?
              AND (start_chapter IS NULL OR start_chapter <= ?)
              AND (end_chapter IS NULL OR end_chapter > ?)
            ORDER BY start_chapter DESC
            LIMIT 20
        ''', (entity_name, current_chapter, current_chapter))
        incoming = cursor.fetchall()

        conn.close()

        if not outgoing and not incoming:
            return f"SQLite备份中暂无关于 {entity_name} 的关系记录。"

        lines = [f"# 🗄️ 关系备份 (SQLite Fallback) - {entity_name}"]

        if outgoing:
            lines.append("\n## 出向关系 (Outgoing):")
            for src, rel, tgt, tgt_type, desc, ch in outgoing:
                ch_tag = f" @Ch{ch}" if ch else ""
                desc_tag = f" ({desc})" if desc else ""
                lines.append(f"  ({src}) --[{rel}]--> ({tgt}:{tgt_type}){desc_tag}{ch_tag}")

        if incoming:
            lines.append("\n## 入向关系 (Incoming):")
            for src, rel, tgt, src_type, desc, ch in incoming:
                ch_tag = f" @Ch{ch}" if ch else ""
                desc_tag = f" ({desc})" if desc else ""
                lines.append(f"  ({src}:{src_type}) --[{rel}]--> ({tgt}){desc_tag}{ch_tag}")

        return "\n".join(lines)

    def query_causal_chain_from_backup(self, event_uid: str, depth: int = 3) -> str:
        """
        🔥 从SQLite备份表追溯因果链 (Neo4j降级模式专用)
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        chain = []
        current_uid = event_uid

        for i in range(depth):
            cursor.execute('''
                SELECT cause_event_uid, description, chapter
                FROM event_backup
                WHERE event_uid = ? AND cause_event_uid IS NOT NULL
            ''', (current_uid,))
            row = cursor.fetchone()

            if not row or not row[0]:
                break

            cause_uid, desc, chapter = row
            chain.append(f"   ⬆️ [Ch{chapter}] 因为: {desc}")
            current_uid = cause_uid

        conn.close()

        if not chain:
            return "（SQLite备份中无明确前因记录）"

        return "导致此事件的因果链 (SQLite Backup):\n" + "\n".join(chain)

    def get_entity_context_with_fallback(self, entity_name: str, current_chapter: int = 999999) -> str:
        """
        🔥 带降级的实体上下文查询

        优先使用Neo4j，失败时自动回退到SQLite备份。
        """
        # 尝试 Neo4j
        if self.graph.is_connected():
            try:
                result = self.graph.query_entity_context(entity_name, current_chapter=current_chapter)
                if result and "暂无" not in result and "不可用" not in result:
                    return result
            except Exception as e:
                print(f"   ⚠️ Neo4j查询失败: {e}, 回退到SQLite备份")

        # 回退到 SQLite
        return self.query_relationships_from_backup(entity_name, current_chapter)
