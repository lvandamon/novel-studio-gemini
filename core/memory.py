from core.schemas import CharacterSchema
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

        # 2. 初始化 ChromaDB
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        self.vector_store = Chroma(
            persist_directory=self.vector_db_path,
            embedding_function=self.embeddings,
            collection_name="novel_content"
        )
        
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
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 伏笔管理表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS foreshadowing (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_created INTEGER,
                content TEXT,
                status TEXT DEFAULT 'active', 
                chapter_resolved INTEGER,
                notes TEXT,
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
                world_state_summary TEXT, 
                chapters_since_last_beat INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()

    # --- 角色操作 ---

    def upsert_character(self, name: str, update_data: Dict[str, Any], chapter_num: int = 0):
        """智能合并角色档案"""
        existing_json = self.get_character(name)
        
        if existing_json:
            merged_data = existing_json.copy()
            
            # 列表型字段取并集
            for list_key in ["personality", "inventory", "goals"]:
                old_list = merged_data.get(list_key, [])
                new_list = update_data.get(list_key, [])
                merged_data[list_key] = list(set(old_list + new_list))
            
            # 字典型字段合并
            old_rel = merged_data.get("relationships", {})
            new_rel = update_data.get("relationships", {})
            old_rel.update(new_rel)
            merged_data["relationships"] = old_rel

            # 其他字段覆盖
            for k, v in update_data.items():
                if k not in ["personality", "inventory", "goals", "relationships", "name"]:
                    merged_data[k] = v
        else:
            merged_data = update_data

        merged_data["last_updated_chapter"] = chapter_num
        merged_data["name"] = name

        # Schema 校验
        validated_data = CharacterSchema(**merged_data)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO characters (name, data) VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET data = ?, updated_at = CURRENT_TIMESTAMP
        ''', (name, validated_data.model_dump_json(), validated_data.model_dump_json()))
        conn.commit()
        conn.close()

    def get_character(self, name: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT data FROM characters WHERE name = ?', (name,))
        row = cursor.fetchone()
        conn.close()
        return json.loads(row[0]) if row else None

    def get_character_details(self, names: List[str], query: str = "") -> str:
        if not names: return "无在场角色详情。"
        details = []
        for name in names:
            data = self.get_character(name)
            if data:
                info = f"--- {name} ---\n"
                for k, v in data.items():
                    if k != "name": info += f"{k}: {v}\n"
                history = self.get_relevant_events(name, query=query, recent_k=3, semantic_k=3)
                if history != "无相关历史事件。":
                    info += f"【关键经历】:\n{history}\n"
                details.append(info)
        return "\n".join(details) if details else "未找到指定角色档案。"

    def get_character_roster_brief(self) -> str:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT name, data FROM characters')
        rows = cursor.fetchall()
        conn.close()
        roster = []
        for name, data_json in rows:
            data = json.loads(data_json)
            roster.append(f"{name}[{data.get('role', '未知')}]")
        return ", ".join(roster) if roster else "暂无角色记录。"

    # --- 章节与节奏 ---

    def update_chapter_summary(self, chapter_num: int, summary: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO chapters (chapter_num) VALUES (?)', (chapter_num,))
        cursor.execute('UPDATE chapters SET summary = ? WHERE chapter_num = ?', (summary, chapter_num))
        cursor.execute('UPDATE narrative_focus SET chapters_since_last_beat = chapters_since_last_beat + 1 WHERE id = 1')
        conn.commit()
        conn.close()

    def get_chapter_summary(self, chapter_num: int) -> str:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT summary FROM chapters WHERE chapter_num = ?', (chapter_num,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] else "暂无摘要。"

    def update_narrative_focus(self, volume: str, arc: str, beat: str, goal: str, conflict: str, state: str, reset_beat: bool = False):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        pacing_clause = "chapters_since_last_beat = 0," if reset_beat else ""
        cursor.execute(f'''
            INSERT INTO narrative_focus (id, current_volume, current_arc, current_beat, current_goal, current_conflict, world_state_summary, chapters_since_last_beat, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                current_volume = excluded.current_volume,
                current_arc = excluded.current_arc,
                current_beat = excluded.current_beat,
                current_goal = excluded.current_goal,
                current_conflict = excluded.current_conflict,
                world_state_summary = excluded.world_state_summary,
                {pacing_clause}
                updated_at = CURRENT_TIMESTAMP
        ''', (volume, arc, beat, goal, conflict, state))
        conn.commit()
        conn.close()

    def get_narrative_focus(self) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT current_volume, current_arc, current_beat, current_goal, current_conflict, world_state_summary, chapters_since_last_beat FROM narrative_focus WHERE id = 1')
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"volume": row[0], "arc": row[1], "beat": row[2], "goal": row[3], "conflict": row[4], "state": row[5], "chapters_since_last_beat": row[6]}
        return {"volume": "序章", "arc": "引导篇", "beat": "背景铺垫", "goal": "确立主角身份", "conflict": "生存危机", "state": "一切尚未开始。", "chapters_since_last_beat": 0}

    # --- 事件与伏笔 ---

    def log_event(self, chapter_num: int, character_name: str, event_type: str, description: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO events (chapter_num, character_name, event_type, description) VALUES (?, ?, ?, ?)', (chapter_num, character_name, event_type, description))
        event_id = cursor.lastrowid
        conn.commit()
        conn.close()
        full_text = f"{character_name} {event_type}: {description}"
        self.event_store.add_documents([Document(page_content=full_text, metadata={"event_id": event_id, "chapter": chapter_num, "character": character_name, "type": event_type})])

    def get_relevant_events(self, character_name: str, query: str = "", recent_k: int = 5, semantic_k: int = 5) -> str:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        candidates = {}
        cursor.execute('SELECT id, chapter_num, description, event_type FROM events WHERE character_name = ? ORDER BY chapter_num DESC LIMIT ?', (character_name, recent_k))
        for row in cursor.fetchall():
            candidates[row[0]] = {"chapter": row[1], "desc": row[2], "type": row[3], "source": "Recent"}
        if query:
            results = self.event_store.similarity_search(query, k=semantic_k, filter={"character": character_name})
            for doc in results:
                evt_id = doc.metadata.get("event_id")
                if evt_id and evt_id not in candidates:
                    candidates[evt_id] = {"chapter": doc.metadata.get("chapter"), "desc": doc.page_content.split(": ", 1)[-1], "type": doc.metadata.get("type"), "source": "Related"}
        conn.close()
        if not candidates: return "无相关历史事件。"
        sorted_events = sorted(candidates.values(), key=lambda x: x["chapter"])
        return "\n".join([f"[{'⚡️' if e['source'] == 'Related' else '🕒'} 第{e['chapter']}章] {e['desc']}" for e in sorted_events])

    def add_foreshadowing(self, chapter_num: int, content: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO foreshadowing (chapter_created, content) VALUES (?, ?)', (chapter_num, content))
        conn.commit()
        conn.close()

    def resolve_foreshadowing(self, clue_id: int, chapter_resolved: int):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('UPDATE foreshadowing SET status = "resolved", chapter_resolved = ? WHERE id = ?', (chapter_resolved, clue_id))
        conn.commit()
        conn.close()

    def get_active_foreshadowing(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT id, chapter_created, content FROM foreshadowing WHERE status = "active"')
        rows = cursor.fetchall()
        conn.close()
        return [{"id": r[0], "chapter": r[1], "content": r[2]} for r in rows]

    # --- 向量存储 ---

    def add_chapter_context(self, text: str, chapter_num: int, metadata: Dict[str, Any] = None):
        if metadata is None: metadata = {}
        metadata.update({"chapter": chapter_num, "type": "chapter_content"})
        self.vector_store.add_documents([Document(page_content=text, metadata=metadata)])

    def query_related_context(self, query: str, k: int = 3) -> str:
        docs = self.vector_store.similarity_search(query, k=k)
        if not docs: return "暂无相关记忆。"
        return "\n".join([f"--- 记忆片段 {i+1} [第 {doc.metadata.get('chapter', '?')} 章] ---\n{doc.page_content}\n" for i, doc in enumerate(docs)])