from core.schemas import CharacterSchema, RealityLayer, ArcStatus, VolumeSchema, ArcSchema
import sqlite3
import json
import os
import uuid
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
        
        # 3. 初始化 Knowledge Graph (Neo4j)
        self.graph = GraphManager()
        
        # 4. 初始化实体提取链 (LLM)
        self.extractor_chain = ENTITY_EXTRACTION_PROMPT | get_deepseek_chat() | StrOutputParser()

    def _init_sqlite(self):
        """初始化 SQLite 表结构 - v2.0 UUID 重构版"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
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
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                current_date TEXT DEFAULT '天道历元年1月1日'
            )
        ''')

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
                notes TEXT
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
        
        conn.commit()
        conn.close()

    # --- 遥测指标 (Narrative Telemetry) ---

    def log_chapter_metrics(self, chapter_num: int, metrics: Dict[str, Any]):
        """记录章节遥测数据"""
        conn = sqlite3.connect(self.db_path)
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
        conn.commit()
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
        获取文风样板 (Style Guide).
        Context-Aware: 根据传入的 tags (如 ['Dark', 'Action']) 检索对应类别的样板。
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        rows = []
        if tags:
            # 尝试匹配 tags 对应的 category
            # 动态构建 SQL
            placeholders = ','.join(['?'] * len(tags))
            # 优先匹配
            sql = f"SELECT category, content FROM style_guide WHERE category IN ({placeholders}) ORDER BY RANDOM() LIMIT ?"
            params = list(tags) + [limit]
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        # 如果没有找到，或者没提供 tags，尝试获取 'General' 或 'Narrative' 作为默认
        if not rows:
            cursor.execute("SELECT category, content FROM style_guide WHERE category IN ('General', 'Narrative', 'Default') ORDER BY RANDOM() LIMIT ?", (limit,))
            rows = cursor.fetchall()
            
        conn.close()
        
        if not rows: return ""
        
        lines = ["# 🖋️ 文风参考 (Style Reference) - 请模仿以下笔触"]
        for cat, content in rows:
            lines.append(f"--- [Example: {cat}] ---\n{content}")
        
        return "\n".join(lines)

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
        self.vector_store.add_documents([
            Document(
                page_content=full_text, 
                metadata={
                    "type": "bible_truth", 
                    "category": category, 
                    "topic": topic, 
                    "entry_id": entry_id
                }
            )
        ])
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
            filter={"type": "bible_truth"}
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

            # C. 物品栏 (Inventory) 特殊处理: 支持增减
            # 1. 添加新物品
            current_inv = set(merged_data.get("inventory", []) or [])
            new_inv = set(update_data.get("inventory", []) or [])
            current_inv.update(new_inv)
            
            # 2. 移除物品 (Explicit Removal)
            removed_items = set(update_data.get("removed_items", []) or [])
            current_inv.difference_update(removed_items)
            
            merged_data["inventory"] = list(current_inv)
            
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
            exclude_keys = overwrite_keys + append_keys + ["relationships", "id", "psychological_state", "inventory", "removed_items"]
            for k, v in update_data.items():
                if k not in exclude_keys and v is not None: 
                    merged_data[k] = v
        else:
            # 全新角色
            merged_data = update_data
            merged_data["id"] = char_id
            
            # 初始化列表 (防止 None)
            for k in ["aliases", "personality", "goals", "inventory", "psychological_history", "dialogue_examples"]:
                if k not in merged_data or merged_data[k] is None:
                    merged_data[k] = []
                    
            if name not in merged_data["aliases"]:
                merged_data["aliases"].append(name)
            
            # 处理 Inventory/Removed logic even for new char (rare but consistent)
            if "removed_items" in merged_data:
                # remove from potentially initial inventory
                inv = set(merged_data.get("inventory", []))
                inv.difference_update(set(merged_data["removed_items"]))
                merged_data["inventory"] = list(inv)
                del merged_data["removed_items"]

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
                info += f"物品栏: {', '.join(inventory) if inventory else '空'}\n"
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

    def get_chapter_summary(self, chapter_num: int) -> str:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT summary FROM chapters WHERE chapter_num = ?', (chapter_num,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] else "暂无摘要。"

    def update_narrative_focus(self, volume: str, arc: str, beat: str, goal: str, conflict: str, state: str, reset_beat: bool = False, current_date: str = None):
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
        
        if current_date:
            update_parts.append("current_date = excluded.current_date")
            val_date = current_date
        else:
            val_date = None

        set_clause = ", ".join(update_parts)
        
        if current_date:
             cursor.execute(f'''
                INSERT INTO narrative_focus (id, current_volume, current_arc, current_beat, current_goal, current_conflict, world_state_summary, chapters_since_last_beat, current_date, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, 0, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    {set_clause}
            ''', (volume, arc, beat, goal, conflict, state, val_date))
        else:
             cursor.execute(f'''
                INSERT INTO narrative_focus (id, current_volume, current_arc, current_beat, current_goal, current_conflict, world_state_summary, chapters_since_last_beat, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    {set_clause}
            ''', (volume, arc, beat, goal, conflict, state))

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
        cursor.execute('SELECT current_volume, current_arc, current_beat, current_goal, current_conflict, world_state_summary, chapters_since_last_beat, current_date FROM narrative_focus WHERE id = 1')
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
                "date": row[7]
            }
        return {
            "volume": "序章", "arc": "引导篇", "beat": "背景铺垫", "goal": "确立主角身份", 
            "conflict": "生存危机", "state": "一切尚未开始。", 
            "chapters_since_last_beat": 0,
            "date": "天道历元年1月1日"
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
        self.event_store.add_documents([Document(page_content=full_text, metadata={"event_id": event_id, "chapter": chapter_num, "character": character_name, "type": event_type, "layer": layer})])

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

    # --- 向量存储与混合检索 ---

    def add_chapter_context(self, text: str, chapter_num: int, metadata: Dict[str, Any] = None):
        if metadata is None: metadata = {}
        metadata.update({"chapter": chapter_num, "type": "chapter_content"})
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

    def query_related_context(self, query: str, k: int = 5) -> str:
        """
        分级混合检索 (Tri-Stage Retrieval):
        1. 语义检索 (Semantic Search): 查找相关情节。
        2. 实体/伏笔锚点 (Entity/Hook Anchor): 强制召回相关未回收伏笔。
        3. 时空临近 (Temporal Proximity): 隐含在语义检索结果中，通过 Re-ranking 提升近期记忆权重。
        """
        final_docs = {} # id -> Document
        
        # --- Stage 1: 宽泛的语义检索 ---
        semantic_docs = self.vector_store.similarity_search(query, k=k)
        for doc in semantic_docs:
            # 假设 page_content 是唯一的 key，或者用 metadata 里的 source + index
            key = doc.page_content[:50] 
            doc.metadata["retrieval_source"] = "Semantic"
            final_docs[key] = doc

        # --- Stage 2: 实体与伏笔关联检索 ---
        # 使用语义实体提取，而非正则匹配
        keywords = self._extract_entities_semantically(query)
        if keywords:
            # 2a. 检查是否有相关联的未回收伏笔
            active_hooks = self.get_active_foreshadowing()
            for hook in active_hooks:
                # 如果伏笔内容包含当前 query 中的关键词
                # 这里的匹配逻辑也可以升级，但目前保留简单的包含匹配，因为 keywords 已经是精准实体了
                for kw in keywords:
                    if kw in hook['content']:
                        # 构造一个虚拟 Document
                        doc = Document(
                            page_content=f"【未回收伏笔】(ID:{hook['id']}) {hook['content']}",
                            metadata={"chapter": hook['chapter'], "type": "foreshadowing", "retrieval_source": "HookMatch"}
                        )
                        final_docs[f"hook_{hook['id']}"] = doc
        
        # --- Stage 3: 结果整合与格式化 ---
        # 简单的重排序逻辑：优先展示 HookMatch，然后是 Semantic
        sorted_docs = sorted(
            final_docs.values(), 
            key=lambda x: (
                0 if x.metadata.get("retrieval_source") == "HookMatch" else 1,
                -x.metadata.get("chapter", 0) # 同优先级下，越新越好
            )
        )

        if not sorted_docs: return "暂无相关记忆。"

        lines = []
        for i, doc in enumerate(sorted_docs):
            source_tag = "⚡️" if doc.metadata.get("retrieval_source") == "Semantic" else "🔗"
            chapter = doc.metadata.get("chapter", "?")
            lines.append(f"--- 记忆片段 {i+1} [{source_tag} 第 {chapter} 章] ---\n{doc.page_content}\n")
            
        return "\n".join(lines)

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
