import tiktoken
from typing import List, Dict, Any, Optional
from core.memory import MemoryManager
import json

class ContextManager:
    """
    分层级上下文管理器 (Hierarchical Context Manager)
    
    层级结构：
    1. Global Layer (世界层): 终极目标、世界规则、当前卷/单元规划。 (Cacheable)
    2. Local Layer (场景层): 当前场景位置、在场角色(Roster)、上一章摘要。 (Dynamic)
    3. Retrieval Layer (检索层): 针对当前情节大纲(Outline)动态检索的事件、伏笔、图谱。 (Highly Dynamic)
    
    Token 预算策略:
    - 优先保住 Global 和 Local (基础连贯性)。
    - 剩余预算大量分配给 Retrieval (细节丰富度)。
    """
    
    def __init__(self, memory_manager: MemoryManager, model_name: str = "gpt-4o"):
        self.memory = memory_manager
        try:
            self.encoder = tiktoken.encoding_for_model(model_name)
        except:
            self.encoder = tiktoken.get_encoding("cl100k_base")
            
        # 默认总预算 (conservative for output room)
        self.total_budget = 12000 
        
        # 基础层预算 (硬性保留)
        self.base_budgets = {
            "global": 2000,
            "local_roster": 1500,
            "prev_summary": 800,
        }

    def _count_tokens(self, text: str) -> int:
        return len(self.encoder.encode(text))

    def _trim_lines_to_budget(self, text: str, budget: int, from_start: bool = True) -> str:
        """按行裁剪文本以适应 token 预算"""
        if not text: return ""
        lines = text.split('\n')
        result = []
        current_tokens = 0
        
        iterator = lines if from_start else reversed(lines)
        
        for line in iterator:
            t = self._count_tokens(line)
            if current_tokens + t > budget:
                break
            result.append(line)
            current_tokens += t
            
        if not from_start:
            result.reverse()
            
        return "\n".join(result)

    def build_director_context(self, chapter_num: int) -> str:
        """
        为 Director (导演) 提供的宏观视角上下文。
        不需要太多细节，需要的是 结构(Structure) 和 状态(State)。
        """
        focus = self.memory.get_narrative_focus()
        active_plan = self.memory.get_active_plan()
        
        # 0. 获取世界圣经 (相关核心设定)
        bible_text = self.memory.get_bible_context(query=focus['goal'])

        # 1. 进度概览
        progress_text = f"当前进度: 第 {chapter_num} 章\n"
        if active_plan["volume"]:
            progress_text += f"卷: {active_plan['volume']['name']} (目标: {active_plan['volume']['goal']})\n"
        if active_plan["arc"]:
            progress_text += f"单元: {active_plan['arc']['name']} (目标: {active_plan['arc']['goal']})\n"
            progress_text += f"单元关键节点: {json.dumps(active_plan['arc']['key_events'], ensure_ascii=False)}\n"
            
        # 2. 叙事焦点状态
        focus_text = f"""
当前节拍: {focus['beat']} (已持续 {focus.get('chapters_since_last_beat', 0)} 章)
当前冲突: {focus['conflict']}
世界状态摘要: {focus['state']}
"""

        # 3. 近期摘要 (最近 10 章，比 Writer 看得远)
        summaries = []
        for i in range(max(1, chapter_num - 10), chapter_num):
            s = self.memory.get_chapter_summary(i)
            summaries.append(f"Ch{i}: {s}")
        recent_history = "\n".join(summaries)
        
        # 4. 活跃伏笔 (导演需要检查哪些该回收了)
        hooks = self.memory.get_active_foreshadowing()
        hooks_text = "\n".join([f"- [ID:{h['id']}] (Ch{h['chapter']}) {h['content']}" for h in hooks]) if hooks else "无活跃伏笔"

        return f"""
{bible_text}

# 🎬 导演控制台

## 1. 宏观进度
{progress_text}

## 2. 叙事状态
{focus_text}

## 3. 待处理伏笔/悬念
{hooks_text}

## 4. 近期剧情流 (Last 10 Chapters)
{recent_history}
"""

    def build_writer_context(self, chapter_num: int, outline: str, active_characters: List[str], scene_location: str, atmosphere: Dict[str, str] = None) -> str:
        """
        为 Writer (作家) 提供的执行视角上下文。
        采用分层构建 + 动态预算。
        """
        # --- 0. World Bible Layer (绝对真理 - 最高优先级) ---
        # 检索与当前情节(outline)和角色(active_characters)相关的绝对规则
        bible_text = self.memory.get_bible_context(query=outline, active_entities=active_characters)
        bible_tokens = self._count_tokens(bible_text)
        
        # 扣除 Bible 的预算 (它不参与动态裁剪，必须保留)
        current_budget = self.total_budget - bible_tokens
        
        # --- 1. Global & Story Layer (世界与剧情脉络) ---
        focus = self.memory.get_narrative_focus()
        active_plan = self.memory.get_active_plan()
        
        # 获取中期记忆 (最近的批量摘要)
        story_so_far = self.memory.get_recent_aggregated_summaries(limit=2)
        # 获取上一章摘要
        prev_summary = self.memory.get_chapter_summary(chapter_num - 1)

        # 构建规划信息
        plan_info = ""
        if active_plan["volume"]:
            plan_info += f"【当前卷】: {active_plan['volume']['name']} (目标: {active_plan['volume']['goal']})\n"
        if active_plan["arc"]:
            plan_info += f"【当前单元】: {active_plan['arc']['name']} (目标: {active_plan['arc']['goal']})\n"

        global_text = f"""
# 🌍 全局层 (Global Context)
【当前目标】: {focus['goal']} 
【当前冲突】: {focus['conflict']} 
【世界基调】: {atmosphere.get('tone', '默认') if atmosphere else '默认'}
【时间】: {focus.get('date', '未知')}

# 📜 剧情脉络 (Story Context)
## 1. 顶层规划
{plan_info}

## 2. 前情提要 (Medium-term Memory)
{story_so_far if story_so_far else "（暂无阶段性综述）"}

## 3. 上章回顾 (Immediate Context)
{prev_summary}
"""
        
        # --- 2. Local Layer (场景与在场者) ---
        # 场景花名册 (Writer 只需要看当前的)
        local_roster = self.memory.get_local_roster(scene_location)
        local_roster_trimmed = self._trim_lines_to_budget(local_roster, self.base_budgets["local_roster"])
        
        local_text = f"""
# 📍 局部层 (Local Context)
【场景地点】: {scene_location}
【感官焦点】: {atmosphere.get('sensory_focus', '无') if atmosphere else '无'}

【场景内角色 (Roster)】:
{local_roster_trimmed}
"""

        # --- 3. Calculating Remaining Budget for Retrieval ---
        used_tokens = self._count_tokens(global_text) + self._count_tokens(local_text)
        remaining_budget = current_budget - used_tokens
        # 至少保留 4000 给检索，否则检索无意义
        retrieval_budget = max(4000, remaining_budget)
        
        # 分配检索预算: 角色详情(40%) + 历史记忆(40%) + 关系图谱(20%)
        budget_chars = int(retrieval_budget * 0.4)
        budget_rag = int(retrieval_budget * 0.4)
        budget_graph = int(retrieval_budget * 0.2)

        # --- 4. Retrieval Layer (动态检索) ---
        
        # A. 角色详情 (基于 Outline 里的行为检索相关经历)
        # 注意: get_character_details 内部已经包含了 query 能力
        char_details = self.memory.get_character_details(active_characters, query=outline)
        char_details_trimmed = self._trim_lines_to_budget(char_details, budget_chars)
        
        # B. RAG 历史记忆 (针对 Outline 的情节)
        # 这里我们检索稍微多一点，然后裁剪
        rag_content = self.memory.query_related_context(outline, k=8)
        rag_trimmed = self._trim_lines_to_budget(rag_content, budget_rag)
        
        # C. 社交图谱 (Social Graph)
        graph_info = ""
        for name in active_characters:
            g = self.memory.get_social_graph(name, current_chapter=chapter_num)
            if "暂无" not in g:
                graph_info += f"[{name}的网络]:\n{g}\n"
        graph_trimmed = self._trim_lines_to_budget(graph_info, budget_graph)

        retrieval_text = f"""
# 🧠 检索层 (Retrieval Context)

## 关键角色档案 (动态)
{char_details_trimmed}

## 相关历史记忆 (RAG)
{rag_trimmed}

## 社交关系网 (Graph)
{graph_trimmed}
"""
        
        # 文风样板 retrieval (Context-Aware)
        style_tags = []
        if atmosphere:
            # 简单的映射逻辑，或是直接使用 tone
            tone = atmosphere.get('tone', '')
            if tone: style_tags.append(tone)
            # 可以扩展更多映射，例如 'Tense' -> 'Action'
            if 'Tense' in tone or 'Dark' in tone:
                style_tags.append('Action')
                style_tags.append('Suspense')
            elif 'Warm' in tone:
                style_tags.append('Dialogue')
        
        style_text = self.memory.get_style_examples(tags=style_tags)

        # --- Final Assembly ---
        # Bible 放在最前面!
        # Bible -> Global -> Local -> Retrieval
        full_context = f"{bible_text}\n{global_text}\n{local_text}\n{style_text}\n{retrieval_text}"
        return full_context
