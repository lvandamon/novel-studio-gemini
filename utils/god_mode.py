import sqlite3
import json
from typing import Dict, Any, List, Optional
from core.memory import MemoryManager

class GodMode:
    """
    上帝模式工具箱 (God Mode Toolkit)
    提供对数据库状态的直接外科手术式修改能力。
    """
    def __init__(self, memory_manager: MemoryManager):
        self.memory = memory_manager
        self.db_path = memory_manager.db_path

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def get_character_data(self, name: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, data FROM characters WHERE name = ?", (name,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            try:
                data = json.loads(row[2])
                # Ensure name is in data
                data['name'] = row[1]
                return data
            except:
                return {"name": row[1], "error": "Invalid JSON"}
        return None

    def save_character_data(self, name: str, new_data: Dict[str, Any]) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            json_str = json.dumps(new_data, ensure_ascii=False, indent=2)
            cursor.execute("UPDATE characters SET data = ? WHERE name = ?", (json_str, name))
            conn.commit()
            return True
        except Exception as e:
            print(f"GodMode Error: {e}")
            return False
        finally:
            conn.close()

    def get_recent_summaries(self, limit: int = 5) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT chapter_num, content 
            FROM summaries 
            WHERE level = 'chapter' 
            ORDER BY chapter_num DESC LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        conn.close()
        
        return [{"chapter": r[0], "content": r[1]} for r in rows]

    def update_chapter_summary(self, chapter_num: int, new_content: str) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                UPDATE summaries 
                SET content = ? 
                WHERE chapter_num = ? AND level = 'chapter'
            ''', (new_content, chapter_num))
            conn.commit()
            return True
        except Exception as e:
            print(f"GodMode Error: {e}")
            return False
        finally:
            conn.close()
            
    def get_all_characters(self) -> List[str]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM characters")
        rows = cursor.fetchall()
        conn.close()
        return [r[0] for r in rows]

    def create_event(self, description: str, chapter_num: int = 0) -> bool:
        """Inject a manual event into history"""
        try:
            self.memory.log_event(
                chapter_num=chapter_num,
                character_name="GOD_MODE",
                event_type="MANUAL_INJECTION",
                description=description,
                layer="Reality"
            )
            return True
        except Exception as e:
            print(f"GodMode Error: {e}")
            return False
