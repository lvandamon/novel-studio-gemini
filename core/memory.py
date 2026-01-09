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
        
        conn.commit()
        conn.close()

    # --- SQLite 操作 ---

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

    def get_all_characters_summary(self) -> str:
        """获取所有角色及其基本状态的简要列表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT name, data FROM characters')
        rows = cursor.fetchall()
        conn.close()
        
        summary = []
        for name, data_json in rows:
            data = json.loads(data_json)
            # 假设角色卡有 'status' 和 'role' 字段
            role = data.get('role', '未知身份')
            status = data.get('status', '未知状态')
            summary.append(f"- {name} ({role}): {status}")
        
        return "\n".join(summary) if summary else "暂无角色记录。"

    # --- VectorDB 操作 ---

    def add_chapter_context(self, text: str, chapter_num: int, metadata: Dict[str, Any] = None):
        """将章节内容存入向量库"""
        if metadata is None:
            metadata = {}
        metadata["chapter"] = chapter_num
        metadata["type"] = "chapter_content"
        
        doc = Document(page_content=text, metadata=metadata)
        self.vector_store.add_documents([doc])
    
    def query_related_context(self, query: str, k: int = 3) -> str:
        """根据关键词检索相关记忆"""
        docs = self.vector_store.similarity_search(query, k=k)
        if not docs:
            return "暂无相关记忆。"
        
        result = []
        for i, doc in enumerate(docs):
            source = f"[第 {doc.metadata.get('chapter', '?')} 章]"
            result.append(f"--- 记忆片段 {i+1} {source} ---\n{doc.page_content}\n")
        
        return "\n".join(result)
