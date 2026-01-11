from core.schemas import CharacterSchema, RealityLayer, ArcStatus, VolumeSchema, ArcSchema
import sqlite3
import json
import os
import uuid
from typing import List, Dict, Any, Optional
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from core.graph_store import GraphManager

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
        
        conn.commit()
        conn.close()

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
        """智能合并角色档案 (支持 UUID 和 别名)"""
        
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
            
            # 列表型字段取并集
            list_keys = ["personality", "inventory", "goals", "dialogue_examples", "aliases", "psychological_history"]
            for list_key in list_keys:
                old_list = merged_data.get(list_key, []) or []
                new_list = update_data.get(list_key, []) or []
                # 简单列表去重 (psychological_history 是 dict list, 不能直接 set, 需要特殊处理)
                if list_key == "psychological_history":
                    # 简单追加即可，或者基于 chapter 去重
                    merged_data[list_key] = old_list + new_list
                else:
                    merged_data[list_key] = list(set(old_list + new_list))
            
            # 字典型字段合并
            old_rel = merged_data.get("relationships", {}) or {}
            new_rel = update_data.get("relationships", {}) or {}
            old_rel.update(new_rel)
            merged_data["relationships"] = old_rel

            # 心理状态特殊处理：如果有更新，则覆盖并记录历史（如果 update_data 里提供了 history，则上面已经合并了，这里主要处理 state）
            if "psychological_state" in update_data and update_data["psychological_state"] != merged_data.get("psychological_state"):
                old_state = merged_data.get("psychological_state", "未知")
                new_state = update_data["psychological_state"]
                # 自动记录一条历史 (如果 update_data 没显式提供 history)
                if not update_data.get("psychological_history"):
                     merged_data["psychological_history"].append({
                        "chapter": chapter_num,
                        "state": new_state,
                        "change_from": old_state,
                        "note": "State update detected"
                    })
                merged_data["psychological_state"] = new_state

            # 其他字段覆盖
            exclude_keys = list_keys + ["relationships", "id", "psychological_state"] # id 和特殊处理字段不允许直接覆盖
            for k, v in update_data.items():
                if k not in exclude_keys and v: 
                    merged_data[k] = v
        else:
            merged_data = update_data
            merged_data["id"] = char_id # 确保 ID 写入 JSON
            merged_data["aliases"] = merged_data.get("aliases", [])
            if name not in merged_data["aliases"]:
                merged_data["aliases"].append(name)

        merged_data["last_updated_chapter"] = chapter_num
        # 始终保持 name 为当前主要名称（如果需要）
        merged_data["name"] = name 

        # 3. 处理别名注册
        if "aliases" in merged_data:
            for alias in merged_data["aliases"]:
                self._register_alias(alias, char_id)

        # 4. Schema 校验
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
                relevant_chars.append(f"- {name} [{role_info}] @ {loc}")
                
        return "\n".join(relevant_chars) if relevant_chars else "（当前地点无其他已知角色）"

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

    def log_event(self, chapter_num: int, character_name: str, event_type: str, description: str, layer: str = "Reality"):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO events (chapter_num, character_name, event_type, description, layer) VALUES (?, ?, ?, ?, ?)', 
                       (chapter_num, character_name, event_type, description, layer))
        event_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        full_text = f"[{layer}] {character_name} {event_type}: {description}"
        self.event_store.add_documents([Document(page_content=full_text, metadata={"event_id": event_id, "chapter": chapter_num, "character": character_name, "type": event_type, "layer": layer})])

    def get_relevant_events(self, character_name: str, query: str = "", recent_k: int = 5, semantic_k: int = 5) -> str:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        candidates = {}
        # 只检索真实发生的事件 (Reality)
        cursor.execute("SELECT id, chapter_num, description, event_type FROM events WHERE character_name = ? AND layer = 'Reality' ORDER BY chapter_num DESC LIMIT ?", (character_name, recent_k))
        for row in cursor.fetchall():
            candidates[row[0]] = {"chapter": row[1], "desc": row[2], "type": row[3], "source": "Recent"}
        
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

    # --- 向量存储与混合检索 ---

    def add_chapter_context(self, text: str, chapter_num: int, metadata: Dict[str, Any] = None):
        if metadata is None: metadata = {}
        metadata.update({"chapter": chapter_num, "type": "chapter_content"})
        self.vector_store.add_documents([Document(page_content=text, metadata=metadata)])

    def _extract_keywords(self, text: str) -> List[str]:
        """简单的关键词提取，目前基于已有角色和物品名，以及常见网文实体词"""
        # 1. 获取所有已知实体名
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT alias FROM character_aliases")
        aliases = [r[0] for r in cursor.fetchall()]
        cursor.execute("SELECT name FROM items")
        items = [r[0] for r in cursor.fetchall()]
        conn.close()
        
        known_entities = set(aliases + items)
        
        # 2. 简单的正则匹配
        import re
        found = []
        for entity in known_entities:
            if entity in text:
                found.append(entity)
        return list(set(found))

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
        keywords = self._extract_keywords(query)
        if keywords:
            # 2a. 检查是否有相关联的未回收伏笔
            active_hooks = self.get_active_foreshadowing()
            for hook in active_hooks:
                # 如果伏笔内容包含当前 query 中的关键词
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
