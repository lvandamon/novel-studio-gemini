import sqlite3
import json
import os
from typing import List, Dict, Any, Optional
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

class MemoryManager:
    def __init__(self, db_path: str = "data/novel.db", vector_db_path: str = "data/vector_store"):
        self.db_path = db_path
        self.vector_db_path = vector_db_path
        
        # 确保数据目录存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(self.vector_db_path, exist_ok=True)

        # 1. 初始化 SQLite
        self._init_sqlite()

        # 2. 初始化 ChromaDB (使用本地 Embedding)
        # 使用轻量级模型 all-MiniLM-L6-v2，速度快效果好
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        self.vector_store = Chroma(
            persist_directory=self.vector_db_path,
            embedding_function=self.embeddings,
            collection_name="novel_content"
        )
        
        # [新增] 事件向量库 (用于联想记忆)
        self.event_store = Chroma(
            persist_directory=self.vector_db_path,
            embedding_function=self.embeddings,
            collection_name="novel_events"
        )

    def _init_sqlite(self):
        """初始化 SQLite 表结构"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 角色表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS characters (
                name TEXT PRIMARY KEY,
                data JSON,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

        # 章节元数据表 (正文主要存 VectorDB，这里存关系)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chapters (
                chapter_num INTEGER PRIMARY KEY,
                title TEXT,
                summary TEXT
            )
        ''')

        # 新增：事件日志表 (Event Log)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_num INTEGER,
                character_name TEXT,
                event_type TEXT, -- e.g., "status_change", "acquisition", "conflict"
                description TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 新增：伏笔管理表 (Foreshadowing / Plot Hooks)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS foreshadowing (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_created INTEGER,
                content TEXT,
                status TEXT DEFAULT 'active', -- active, resolved, ignored
                chapter_resolved INTEGER,
                notes TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # [新增] 全局叙事焦点表 (Singleton: 永远只有一行数据 ID=1)
        # 升级：增加 Arc (单元) 和 Beat (节拍) 字段
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS narrative_focus (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                current_volume TEXT,      -- e.g. "第一卷：云起龙骧"
                current_arc TEXT,         -- e.g. "青云门入门篇"
                current_beat TEXT,        -- e.g. "激励事件 (Inciting Incident)"
                current_goal TEXT,        -- e.g. "通过入门考核"
                current_conflict TEXT,    -- e.g. "资质低劣受人嘲讽"
                world_state_summary TEXT, 
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # [新增] 结构日志表 (用于记录卷/单元的历史)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS structure_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                struct_type TEXT,    -- "volume" or "arc"
                name TEXT,
                description TEXT,
                start_chapter INTEGER,
                end_chapter INTEGER, -- NULL until completed
                status TEXT DEFAULT 'active'
            )
        ''')
        
        conn.commit()
        conn.close()

    # --- SQLite 操作 ---

    def add_foreshadowing(self, chapter_num: int, content: str):
        """新增伏笔"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO foreshadowing (chapter_created, content) VALUES (?, ?)', (chapter_num, content))
        conn.commit()
        conn.close()

    def resolve_foreshadowing(self, clue_id: int, chapter_resolved: int):
        """标记伏笔已回收"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('UPDATE foreshadowing SET status = "resolved", chapter_resolved = ? WHERE id = ?', (chapter_resolved, clue_id))
        conn.commit()
        conn.close()

    def get_active_foreshadowing(self) -> List[Dict[str, Any]]:
        """获取所有未回收的伏笔"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT id, chapter_created, content FROM foreshadowing WHERE status = "active"')
        rows = cursor.fetchall()
        conn.close()
        return [{"id": r[0], "chapter": r[1], "content": r[2]} for r in rows]

    def update_chapter_summary(self, chapter_num: int, summary: str):
        """更新章节摘要"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # 确保章节记录存在
        cursor.execute('INSERT OR IGNORE INTO chapters (chapter_num) VALUES (?)', (chapter_num,))
        cursor.execute('UPDATE chapters SET summary = ? WHERE chapter_num = ?', (summary, chapter_num))
        conn.commit()
        conn.close()
    
    def get_chapter_summary(self, chapter_num: int) -> str:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT summary FROM chapters WHERE chapter_num = ?', (chapter_num,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] else "暂无摘要。"

    def log_event(self, chapter_num: int, character_name: str, event_type: str, description: str):
        """记录关键事件 (双写：SQLite + ChromaDB)"""
        # 1. 写入 SQLite (作为 Source of Truth)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO events (chapter_num, character_name, event_type, description)
            VALUES (?, ?, ?, ?)
        ''', (chapter_num, character_name, event_type, description))
        event_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # 2. 写入 ChromaDB (用于语义检索)
        # 构造富文本内容，增加检索命中率
        full_text = f"{character_name} {event_type}: {description}"
        metadata = {
            "event_id": event_id,
            "chapter": chapter_num,
            "character": character_name,
            "type": event_type
        }
        self.event_store.add_documents([Document(page_content=full_text, metadata=metadata)])

    def get_relevant_events(self, character_name: str, query: str = "", recent_k: int = 5, semantic_k: int = 5) -> str:
        """
        [核心] 混合检索事件历史
        结合 '最近发生' (Short-term) 和 '语义相关' (Long-term)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        candidates = {} # 使用 dict 去重: event_id -> {data}

        # 1. 获取最近事件 (Recency)
        cursor.execute('''
            SELECT id, chapter_num, description, event_type 
            FROM events 
            WHERE character_name = ? 
            ORDER BY chapter_num DESC 
            LIMIT ?
        ''', (character_name, recent_k))
        
        for row in cursor.fetchall():
            candidates[row[0]] = {
                "chapter": row[1], 
                "desc": row[2], 
                "type": row[3], 
                "source": "Recent"
            }

        # 2. 获取语义相关事件 (Relevance) - 仅当有查询意图时
        if query:
            # 使用 filter 限制只检索该角色的事件
            results = self.event_store.similarity_search(
                query, 
                k=semantic_k,
                filter={"character": character_name}
            )
            
            for doc in results:
                evt_id = doc.metadata.get("event_id")
                if evt_id and evt_id not in candidates:
                    # 需要回查 SQLite 获取准确的 chapter 和 description (或者直接信赖 metadata)
                    # 这里为了性能直接用 metadata，但要注意 metadata 和 SQLite 的同步
                    candidates[evt_id] = {
                        "chapter": doc.metadata.get("chapter"),
                        "desc": doc.page_content.split(": ", 1)[-1], # 简单解析
                        "type": doc.metadata.get("type"),
                        "source": "Related"
                    }

        conn.close()
        
        # 3. 排序与格式化
        if not candidates:
            return "无相关历史事件。"
            
        # 按章节号从小到大排序 (Timeline Order)
        sorted_events = sorted(candidates.values(), key=lambda x: x["chapter"])
        
        history_lines = []
        for evt in sorted_events:
            tag = "⚡️" if evt["source"] == "Related" else "🕒"
            history_lines.append(f"[{tag} 第{evt['chapter']}章] {evt['desc']}")
            
        return "\n".join(history_lines)

    # 兼容旧接口，只需保留签名，内部调用新逻辑
    def get_character_event_history(self, character_name: str, limit: int = 5) -> str:
        return self.get_relevant_events(character_name, recent_k=limit)

    def get_recent_events(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近发生的全局事件 (用于 Dashboard 展示)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT chapter_num, character_name, event_type, description, timestamp 
            FROM events 
            ORDER BY id DESC 
            LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        conn.close()
        
        events = []
        for r in rows:
            events.append({
                "chapter": r[0],
                "character": r[1],
                "type": r[2],
                "description": r[3],
                "time": r[4]
            })
        return events

    def upsert_character(self, name: str, data: Dict[str, Any]):
        """更新或插入角色卡"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO characters (name, data) VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET data = ?, updated_at = CURRENT_TIMESTAMP
        ''', (name, json.dumps(data, ensure_ascii=False), json.dumps(data, ensure_ascii=False)))
        conn.commit()
        conn.close()

    def get_character(self, name: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT data FROM characters WHERE name = ?', (name,))
        row = cursor.fetchone()
        conn.close()
        return json.loads(row[0]) if row else None

    def get_all_characters_list(self) -> List[Dict[str, Any]]:
        """获取所有角色的完整数据列表，用于前端表格展示"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT name, data FROM characters')
        rows = cursor.fetchall()
        conn.close()
        
        chars = []
        for name, data_json in rows:
            data = json.loads(data_json)
            if "name" not in data: data["name"] = name
            chars.append(data)
        return chars

    def get_character_details(self, names: List[str], query: str = "") -> str:
        """获取指定角色的详细档案 (Tier 2 Context)"""
        if not names:
            return "无在场角色详情。"
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 动态构建查询
        placeholders = ','.join('?' for _ in names)
        cursor.execute(f'SELECT name, data FROM characters WHERE name IN ({placeholders})', names)
        rows = cursor.fetchall()
        conn.close()
        
        details = []
        for name, data_json in rows:
            data = json.loads(data_json)
            # 格式化为易读的文本块
            info = f"--- {name} ---\n"
            for k, v in data.items():
                if k != "name": # 名字已经在标题里了
                    info += f"{k}: {v}\n"
            
            # [升级] 使用混合检索获取相关经历
            # 如果有 query (如当前大纲)，会尝试检索语义相关的旧事
            history = self.get_relevant_events(name, query=query, recent_k=3, semantic_k=3)
            if history != "无相关历史事件。":
                info += f"【关键经历 (混合检索)】:\n{history}\n"
                
            details.append(info)
            
        return "\n".join(details) if details else "未找到指定角色档案。"

    def get_character_roster_brief(self) -> str:
        """获取所有角色的极简花名册 (Tier 3 Context - 仅姓名和身份，防幻觉)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT name, data FROM characters')
        rows = cursor.fetchall()
        conn.close()
        
        roster = []
        for name, data_json in rows:
            data = json.loads(data_json)
            role = data.get('role', '未知')
            # 极简模式：萧风[主角], 林月[师妹]
            roster.append(f"{name}[{role}]")
        
        return ", ".join(roster) if roster else "暂无角色记录。"

    def update_narrative_focus(self, volume: str, arc: str, beat: str, goal: str, conflict: str, state: str):
        """更新全局叙事焦点 (覆盖式更新)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 1. 更新 Focus 表
        # 检查列是否存在 (为了兼容旧数据库文件，生产环境应该用 Migration，这里简单处理：Drop recreate 或者 alter)
        # 简单起见，我们假设用户是全新运行，或者手动处理。
        # 如果是开发环境，简单粗暴一点：
        try:
            cursor.execute('''
                INSERT INTO narrative_focus (id, current_volume, current_arc, current_beat, current_goal, current_conflict, world_state_summary, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    current_volume = excluded.current_volume,
                    current_arc = excluded.current_arc,
                    current_beat = excluded.current_beat,
                    current_goal = excluded.current_goal,
                    current_conflict = excluded.current_conflict,
                    world_state_summary = excluded.world_state_summary,
                    updated_at = CURRENT_TIMESTAMP
            ''', (volume, arc, beat, goal, conflict, state))
        except sqlite3.OperationalError:
            #不仅是列不对，可能是表结构不对。这里为了演示，如果报错提示缺少列，则暴力重建表 (慎用!)
            # 实际项目中请使用 ALTER TABLE
            print("⚠️ 检测到数据库结构过期，正在尝试自动迁移 narrative_focus...")
            cursor.execute('DROP TABLE narrative_focus')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS narrative_focus (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    current_volume TEXT,
                    current_arc TEXT,
                    current_beat TEXT,
                    current_goal TEXT,
                    current_conflict TEXT,
                    world_state_summary TEXT, 
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                INSERT INTO narrative_focus (id, current_volume, current_arc, current_beat, current_goal, current_conflict, world_state_summary, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (volume, arc, beat, goal, conflict, state))

        conn.commit()
        conn.close()

    def get_narrative_focus(self) -> Dict[str, str]:
        """获取当前的全局叙事焦点"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT current_volume, current_arc, current_beat, current_goal, current_conflict, world_state_summary FROM narrative_focus WHERE id = 1')
            row = cursor.fetchone()
        except sqlite3.OperationalError:
            row = None # 表结构可能不对

        conn.close()

        if row:
            return {
                "volume": row[0],
                "arc": row[1],
                "beat": row[2],
                "goal": row[3],
                "conflict": row[4],
                "state": row[5]
            }
        else:
            # 默认初始状态
            return {
                "volume": "序章",
                "arc": "引导篇",
                "beat": "背景铺垫",
                "goal": "确立主角身份",
                "conflict": "生存危机",
                "state": "一切尚未开始。"
            }

    # --- VectorDB 操作 ---

    def add_chapter_context(self, text: str, chapter_num: int, metadata: Dict[str, Any] = None):
        """将章节内容存入向量库"""
        if metadata is None:
            metadata = {}
        metadata["chapter"] = chapter_num
        metadata["type"] = "chapter_content"
        
        doc = Document(page_content=text, metadata=metadata)
        self.vector_store.add_documents([doc])
    
    def search_related_docs(self, query: str, k: int = 3) -> List[Document]:
        """(底层方法) 根据关键词检索相关 Document 对象"""
        return self.vector_store.similarity_search(query, k=k)

    def query_related_context(self, query: str, k: int = 3) -> str:
        """根据关键词检索相关记忆 (返回格式化字符串)"""
        docs = self.search_related_docs(query, k)
        if not docs:
            return "暂无相关记忆。"
        
        result = []
        for i, doc in enumerate(docs):
            source = f"[第 {doc.metadata.get('chapter', '?')} 章]"
            result.append(f"--- 记忆片段 {i+1} {source} ---\n{doc.page_content}\n")
        
        return "\n".join(result)
