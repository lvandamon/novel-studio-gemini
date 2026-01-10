from typing import List, Dict, Any
from core.memory import MemoryManager

class ContextManager:
    def __init__(self, memory_manager: MemoryManager):
        self.memory = memory_manager

    def build_editor_context(self, chapter_num: int, summary: str) -> str:
        """
        为 Editor (主编) 组装上下文。
        Editor 需要宏观视角，因此侧重于：全局目标 + 上一章摘要 + 简单的角色状态 + 未回收的伏笔。
        """
        # 1. Global Context (Tier 1) - 动态从数据库获取
        focus = self.memory.get_narrative_focus()
        global_context = f"""
【当前卷】：{focus['volume']}
【当前单元 (Arc)】：{focus['arc']}
【当前节拍 (Beat)】：{focus['beat']} (请严格遵循此节拍的叙事功能)
【本单元目标】：{focus['goal']}
【核心冲突】：{focus['conflict']}
【世界动态】：{focus['state']}
"""
        
        # 2. Roster (Tier 3) - 让 Editor 知道有哪些人可用
        roster = self.memory.get_character_roster_brief()
        
        # 3. Foreshadowing (Tier 1.5) - 提醒填坑
        active_hooks = self.memory.get_active_foreshadowing()
        if active_hooks:
            hooks_text = "\n".join([f"- [ID:{h['id']}] {h['content']}" for h in active_hooks])
            hooks_section = f"【待回收伏笔 (请尝试推进)】：\n{hooks_text}"
        else:
            hooks_section = "【待回收伏笔】：暂无。"
        
        return f"""
{global_context}

{hooks_section}

【可用角色花名册】：
{roster}

【前情提要 (第 {chapter_num - 1} 章)】：
{summary}
"""

    def build_writer_context(self, outline: str, active_characters: List[str]) -> str:
        """
        为 Writer (作家) 组装上下文。
        Writer 需要微观细节，因此侧重于：在场角色详情 + RAG 检索的场景记忆。
        """
        # 1. Tier 1: Global Context (简略版，提醒基调 + 当前目标)
        focus = self.memory.get_narrative_focus()
        global_tier = f"""
【世界观基调】：修仙、残酷、凡人流。核心规则：境界压制不可逆。
【当前进度】：{focus['arc']} -> {focus['beat']}
【当前焦点】：{focus['goal']} (冲突：{focus['conflict']})
"""

        # 2. Tier 2: Active Characters (在场角色 - 详细)
        # 只有大纲里提到的人，才加载详细卡片
        # [升级] 将 outline 作为 query 传入，激活混合检索
        active_char_details = self.memory.get_character_details(active_characters, query=outline)

        # 3. Tier 3: Roster (不在场角色 - 仅名字，防幻觉)
        roster = self.memory.get_character_roster_brief()

        # 4. Tier 4: RAG Memory (相关环境/设定)
        # 使用大纲内容作为 Query 去检索之前的伏笔或设定
        rag_context = self.memory.query_related_context(outline, k=2)

        return f"""
{global_tier}

【在场角色详情 (重点参考)】：
{active_char_details}

【其他已知角色 (仅供提及)】：
{roster}

【相关历史记忆/设定】：
{rag_context}
"""
