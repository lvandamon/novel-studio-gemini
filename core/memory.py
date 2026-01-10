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
        
        conn.commit()
        conn.close()

    # --- SQLite 操作 ---

    def log_event(self, chapter_num: int, character_name: str, event_type: str, description: str):
        """记录关键事件"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO events (chapter_num, character_name, event_type, description)
            VALUES (?, ?, ?, ?)
        ''', (chapter_num, character_name, event_type, description))
        conn.commit()
        conn.close()

    def get_character_event_history(self, character_name: str, limit: int = 5) -> str:
        """获取指定角色的最近关键事件"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT chapter_num, description FROM events 
            WHERE character_name = ? 
            ORDER BY chapter_num DESC 
            LIMIT ?
        ''', (character_name, limit))
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return "无相关历史事件。"
        
        history = []
        for chapter, desc in rows:
            history.append(f"[第 {chapter} 章] {desc}")
        return "\n".join(history)

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

    def get_character_details(self, names: List[str]) -> str:
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
            
            # [新增] 追加历史事件
            history = self.get_character_event_history(name, limit=3)
            if history != "无相关历史事件。":
                info += f"【近期经历】:\n{history}\n"
                
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
