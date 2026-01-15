import sqlite3
import json
from typing import List, Dict, Any, Optional
from core.schemas import AnchorStatus

class DynamicAnchorManager:
    """
    🔥 P9新增: 动态锚点管理器 (Dynamic Anchor Manager)
    
    负责管理角色性格的"代际演化" (Epoch Evolution)。
    核心逻辑:
    1. 角色处于特定的"代际" (Epoch) 中 (如: "青涩期" -> "黑化期")。
    2. 只有当前代际的锚点 + 未被覆盖的底层本能 是生效的。
    3. 当发生"性格质变"事件时, 旧锚点被击碎/归档, 新锚点诞生。
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _get_connection(self):
        return sqlite3.connect(self.db_path, timeout=30.0)

    def get_current_epoch(self, character_name: str) -> Optional[Dict[str, Any]]:
        """获取角色当前的代际"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, epoch_name, description, start_chapter 
            FROM character_epochs 
            WHERE character_name = ? AND end_chapter IS NULL
            ORDER BY start_chapter DESC LIMIT 1
        ''', (character_name,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "start_chapter": row[3]
            }
        return None

    def start_new_epoch(self, character_name: str, new_epoch_name: str, description: str, 
                       trigger_event: str, chapter_num: int) -> int:
        """
        开启新的性格代际。自动结束上一个代际。
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 1. 结束旧代际
        cursor.execute('''
            UPDATE character_epochs 
            SET end_chapter = ? 
            WHERE character_name = ? AND end_chapter IS NULL
        ''', (chapter_num - 1, character_name))
        
        # 2. 创建新代际
        cursor.execute('''
            INSERT INTO character_epochs (character_name, epoch_name, description, start_chapter, evolution_trigger)
            VALUES (?, ?, ?, ?, ?)
        ''', (character_name, new_epoch_name, description, chapter_num, trigger_event))
        
        new_epoch_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        print(f"   🧬 [Evolution] {character_name} 进入新阶段: 【{new_epoch_name}】 (Ch{chapter_num})")
        return new_epoch_id

    def add_anchor(self, character_name: str, category: str, content: str, 
                  tags: List[str] = None, epoch_id: int = None, chapter_num: int = 0):
        """添加锚点，自动关联当前代际"""
        if tags is None: tags = []
        
        # 如果未指定 epoch_id，自动查找当前 epoch
        if epoch_id is None:
            epoch = self.get_current_epoch(character_name)
            if epoch:
                epoch_id = epoch['id']
            else:
                # 如果没有代际，创建一个默认的 "初始期"
                epoch_id = self.start_new_epoch(character_name, "初始设定", "角色登场时的初始状态", "Initial Creation", 1)

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO character_anchors (character_name, category, content, tags, epoch_id, status, is_active) 
            VALUES (?, ?, ?, ?, ?, ?, 1)
        ''', (character_name, category, content, json.dumps(tags), epoch_id, AnchorStatus.ACTIVE.value))
        conn.commit()
        conn.close()
        print(f"   ⚓️ Anchor Added: {character_name} [{category}] (Epoch {epoch_id})")

    def add_trauma(self, character_name: str, content: str, origin_event: str, intensity: int = 5):
        """
        🔥 P10新增: 添加心理创伤/执念 (Trauma/Obsession)
        创伤是一种特殊的负面锚点，直接影响潜意识(System Prompt)。
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 使用特殊的 category = 'Trauma'
        # 存储 intensity 到 tags 或 metadata? 这里简单存入 tags
        tags = ["Trauma", f"Intensity:{intensity}", origin_event]
        
        cursor.execute('''
            INSERT INTO character_anchors (character_name, category, content, tags, status, is_active) 
            VALUES (?, 'Trauma', ?, ?, 'active', 1)
        ''', (character_name, content, json.dumps(tags)))
        
        conn.commit()
        conn.close()
        print(f"   💔 Trauma Added: {character_name} -> {content} (Int:{intensity})")

    def shatter_anchor(self, anchor_id: int, reason: str, chapter_num: int):
        """击碎/废弃某个锚点"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE character_anchors 
            SET status = ?, is_active = 0, evolution_logic = ? 
            WHERE id = ?
        ''', (AnchorStatus.SHATTERED.value, reason, anchor_id))
        conn.commit()
        conn.close()
        print(f"   💥 Anchor Shattered: ID {anchor_id} -> {reason}")

    def get_effective_anchors_text(self, character_name: str) -> str:
        """
        获取角色当前的"有效锚点"文本 (用于注入 Prompt)。
        
        策略:
        1. 显示当前代际名称。
        2. 列出所有 status='active' 的锚点。
        3. (可选) 列出最近被击碎的锚点作为"性格伤痕"。
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 获取代际信息
        epoch = self.get_current_epoch(character_name)
        epoch_info = f"当前阶段: 【{epoch['name']}】" if epoch else "当前阶段: 初始状态"
        if epoch and epoch.get('description'):
            epoch_info += f" ({epoch['description']})"
            
        # 获取活跃锚点
        cursor.execute('''
            SELECT category, content, tags 
            FROM character_anchors 
            WHERE character_name = ? AND status = 'active'
        ''', (character_name,))
        active_rows = cursor.fetchall()
        
        # 获取最近击碎的锚点 (作为性格背景)
        cursor.execute('''
            SELECT category, content, evolution_logic 
            FROM character_anchors 
            WHERE character_name = ? AND status = 'shattered'
            ORDER BY id DESC LIMIT 2
        ''', (character_name,))
        shattered_rows = cursor.fetchall()
        
        conn.close()
        
        if not active_rows and not shattered_rows:
            return ""
            
        lines = [f"### ⚓️ {character_name} 的性格锚点 (Personality Anchors) - {epoch_info}"]
        
        if active_rows:
            lines.append("【绝对准则 (Active Anchors)】:")
            for cat, content, tags_json in active_rows:
                if cat == 'Trauma': continue # Skip trauma here, handle below
                
                tags = json.loads(tags_json) if tags_json else []
                tag_str = f" [触发: {', '.join(tags)}]" if tags else ""
                lines.append(f"- [{cat}]{tag_str} {content}")

        # Extract Traumas
        traumas = [row for row in active_rows if row[0] == 'Trauma']
        if traumas:
            lines.append("【💔 心理创伤/执念 (Subconscious Scars)】:")
            for _, content, tags_json in traumas:
                tags = json.loads(tags_json) if tags_json else []
                # Extract intensity and origin
                intensity = "5"
                origin = "Unknown"
                for t in tags:
                    if t.startswith("Intensity:"): intensity = t.split(":")[1]
                    elif t not in ["Trauma", "Intensity"]: origin = t
                
                lines.append(f"- (Level {intensity}) {content} [源于: {origin}]")
                lines.append(f"  -> 指令: 在涉及相关情境时，必须体现出痛苦、回避或偏执。")

        if shattered_rows:
            lines.append("【已破碎的旧我 (Shattered Past - Do NOT Revert)】:")
            for cat, content, logic in shattered_rows:
                lines.append(f"- (已弃用) [{cat}] {content} -> 因 [{logic}] 而改变")
                
        return "\n".join(lines)
