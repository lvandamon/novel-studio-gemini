import tiktoken
from typing import List, Dict, Any, Optional
from core.memory import MemoryManager

class ContextManager:
    def __init__(self, memory_manager: MemoryManager, model_name: str = "gpt-4o"):
        self.memory = memory_manager
        # 使用 tiktoken 计算 token，o1/v3/r1 的编码器与 gpt-4o 基本一致
        try:
            self.encoder = tiktoken.encoding_for_model(model_name)
        except:
            self.encoder = tiktoken.get_encoding("cl100k_base")
        
        # 默认 Token 预算分配 (总计约 16k-32k 比较稳妥)
        self.default_budgets = {
            "plan": 1000,
            "roster": 2000,
            "char_details": 4000,
            "rag_memory": 6000,
            "summary": 1000,
            "outline": 1000
        }

    def _count_tokens(self, text: str) -> int:
        return len(self.encoder.encode(text))

    def _trim_to_budget(self, items: List[str], budget: int) -> str:
        """按预算裁剪列表项，从后往前保留（假设后面的是更相关的，或者通过排序决定）"""
        current_text = ""
        current_tokens = 0
        # 这里采用保留前部的策略，或者由调用者排序好
        result = []
        for item in items:
            item_tokens = self._count_tokens(item)
            if current_tokens + item_tokens <= budget:
                result.append(item)
                current_tokens += item_tokens
            else:
                break
        return "\n".join(result)

    def build_editor_context(self, chapter_num: int, summary: str) -> str:
        """
        为 Editor (主编) 组装上下文，带 Token 控制。
        """
        focus = self.memory.get_narrative_focus()
        active_plan = self.memory.get_active_plan()
        
        # 1. Plan Section
        plan_text = ""
        if active_plan["volume"]:
            vol = active_plan["volume"]
            plan_text += f"【当前卷 ({vol['name']})】：{vol['goal']}\n"
        if active_plan["arc"]:
            arc = active_plan["arc"]
            plan_text += f"【当前单元 ({arc['name']})】：{arc['goal']}\n"
            plan_text += f"  -> 关键节点规划: [{', '.join(arc['key_events']) or '无'}]\n"

        # 2. Roster
        roster_text = self.memory.get_character_roster_brief()
        roster_trimmed = self._trim_to_budget(roster_text.split('\n'), self.default_budgets["roster"])

        # 3. Hooks
        active_hooks = self.memory.get_active_foreshadowing()
        hooks_text = "\n".join([f"- [ID:{h['id']}] {h['content']}" for h in active_hooks]) if active_hooks else "暂无。"

        return f"""
【当前进度】：第 {chapter_num} 章
{plan_text}
【当前节拍】：{focus['beat']} (已持续 {focus.get('chapters_since_last_beat', 0)} 章)
【世界动态】：{focus['state']}

【待回收伏笔】：
{hooks_text}

【全球角色分布】：
{roster_trimmed}

【前情提要】：
{summary}
"""

    def build_writer_context(self, chapter_num: int, outline: str, active_characters: List[str], scene_location: str = "未知", atmosphere: Dict[str, str] = None) -> str:
        """
        为 Writer (作家) 组装上下文，带分级 Token 预算控制。
        """
        focus = self.memory.get_narrative_focus()
        
        # 1. 核心层 (Global Tier) - 必须保留
        atm_text = f"基调: {atmosphere.get('tone', '默认')}, 感官: {atmosphere.get('sensory_focus', '均衡')}" if atmosphere else ""
        global_tier = f"【目标】:{focus['goal']} \n【场景】:{scene_location} \n【氛围】:{atm_text}"

        # 2. 角色层 (Character Tier)
        # 获取详细档案，并根据预算裁剪（如果角色太多，缩减每个角色的描述）
        char_details = self.memory.get_character_details(active_characters, query=outline)
        # TODO: 以后可以实现更精细的按角色权重裁剪
        char_details_trimmed = self._trim_to_budget(char_details.split('---'), self.default_budgets["char_details"])

        # 3. 图谱层 (Social Graph)
        social_info = ""
        for name in active_characters:
            graph_data = self.memory.get_social_graph(name, current_chapter=chapter_num)
            if "暂无" not in graph_data:
                social_info += f"{name}关系: {graph_data}\n"
        social_trimmed = self._trim_to_budget(social_info.split('\n'), 1000) # 图谱预算较小

        # 4. 记忆层 (RAG Memory)
        rag_context = self.memory.query_related_context(outline, k=8)
        # 记忆通常比较碎，按片段裁剪
        rag_trimmed = self._trim_to_budget(rag_context.split('---'), self.default_budgets["rag_memory"])

        return f"""
{global_tier}

【关键角色档案】：
{char_details_trimmed}

【人际关系网】：
{social_trimmed}

【相关历史记忆/伏笔】：
{rag_trimmed}
"""