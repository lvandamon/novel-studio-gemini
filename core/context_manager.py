from typing import List, Dict, Any
from core.memory import MemoryManager

class ContextManager:
    def __init__(self, memory_manager: MemoryManager):
        self.memory = memory_manager

    def build_editor_context(self, chapter_num: int, summary: str) -> str:
        """
        为 Editor (主编) 组装上下文。
        """
        # 1. Global Context & Plan
        focus = self.memory.get_narrative_focus()
        active_plan = self.memory.get_active_plan()
        
        plan_text = ""
        if active_plan["volume"]:
            vol = active_plan["volume"]
            plan_text += f"【当前卷 ({vol['name']})】：{vol['goal']}\n"
        if active_plan["arc"]:
            arc = active_plan["arc"]
            events_str = ", ".join(arc['key_events'])
            plan_text += f"【当前单元 ({arc['name']})】：{arc['goal']}\n"
            plan_text += f"  -> 关键节点规划: [{events_str}]\n"

        pacing_warning = ""
        if focus.get('chapters_since_last_beat', 0) >= 3:
            pacing_warning = f"\n⚠️ 【节奏警告】：当前节拍已持续 {focus['chapters_since_last_beat']} 章，请加速！"

        global_context = f"""
【当前进度】：第 {chapter_num} 章
{plan_text}
【当前节拍】：{focus['beat']} {pacing_warning}
【本节拍冲突】：{focus['conflict']}
【世界动态】：{focus['state']}
"""
        
        # 2. Roster - Editor 看到按地点分组的全景
        roster = self.memory.get_character_roster_brief()
        
        # 3. Foreshadowing
        active_hooks = self.memory.get_active_foreshadowing()
        hooks_text = "\n".join([f"- [ID:{h['id']}] {h['content']}" for h in active_hooks]) if active_hooks else "暂无。"
        
        return f"""
{global_context}

【待回收伏笔】：
{hooks_text}

【全球角色地理分布】：
{roster}

【前情提要 (第 {chapter_num - 1} 章)】：
{summary}
"""

    def build_writer_context(self, chapter_num: int, outline: str, active_characters: List[str], scene_location: str = "未知", atmosphere: Dict[str, str] = None) -> str:
        """
        为 Writer (作家) 组装上下文。
        """
        # 1. Global Tier
        focus = self.memory.get_narrative_focus()
        
        atm_text = ""
        if atmosphere:
            atm_text = f"""
【环境氛围 (Atmosphere)】：
- 基调 (Tone): {atmosphere.get('tone', '默认')}
- 感官侧重 (Sensory): {atmosphere.get('sensory_focus', '均衡')}
- 视觉色调 (Color): {atmosphere.get('color_palette', '正常')}
"""

        global_tier = f"""
【世界观基调】：修仙、残酷、凡人流。
【当前目标】：{focus['goal']}
【当前场景】：{scene_location}
{atm_text}
"""

        # 2. Tier 2: Active Characters (详细档案)
        active_char_details = self.memory.get_character_details(active_characters, query=outline)
        
        # 3. Tier 3: Social Graph (基于真实章节号的过滤)
        social_graph_info = ""
        for name in active_characters:
            graph_data = self.memory.get_social_graph(name, current_chapter=chapter_num)
            if graph_data and "暂无" not in graph_data and "未连接" not in graph_data:
                social_graph_info += f"--- {name} 的人际关系网 (截至第 {chapter_num} 章) ---\n{graph_data}\n"

        # 4. Tier 4: Local Roster (地理围栏)
        local_roster = self.memory.get_local_roster(current_location=scene_location)

        # 5. Tier 5: RAG Memory (混合检索)
        rag_context = self.memory.query_related_context(outline, k=5)

        return f"""
{global_tier}

【在场角色详细档案】：
{active_char_details}

【人物关系图谱 (逻辑一致性)】：
{social_graph_info}

【本地及重要人物名单】：
{local_roster}

【相关历史记忆/伏笔】：
{rag_context}
"""
