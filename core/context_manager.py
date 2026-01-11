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
            
        # 默认总预算 (32k for deepseek-v3/r1 long context)
        self.total_budget = 32000 
        
        # 基础层预算 (硬性保留)
        self.base_budgets = {
            "global": 4000,
            "local_roster": 3000,
            "prev_summary": 2000,
            "vocabulary": 1000,
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

    def _build_vocabulary_constraints(self, volume_name: str, arc_name: str) -> str:
        """
        构建动态词表约束 (Dynamic Vocabulary Constraints)。
        从世界圣经中检索当前阶段的禁词、推荐词。
        """
        # 检索 Terminology 相关的圣经条目
        vocab_context = self.memory.get_bible_context(query=f"{volume_name} {arc_name} 术语 词汇 禁忌语")
        
        # 基础通用约束 (Hardcoded Baseline)
        baseline = """
### 🚫 词汇禁区 (Vocabulary Taboos)
- 严禁出现现代科技词汇 (如: 信号, 逻辑, 降维打击, 量子, 甚至“思考方式”等现代口语)。
- 严禁出现 OOC 网络热词。
- 严禁出现非本世界观的计量单位 (除非圣经另有规定)。

### ✅ 推荐词汇 (Recommended Lexicon)
- 使用古雅、稳重的半文言或正统网文仙侠笔触。
- 动作描写优先使用具体的武学方位和劲力描述。
"""
        if vocab_context:
            return f"{baseline}\n### 🌍 当前阶段特定词表:\n{vocab_context}"
        return baseline

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

    def _analyze_plot_intent(self, outline: str) -> Dict[str, Any]:
        """
        [核心逻辑] 意图解析器：分析大纲需要什么样的背景知识。
        """
        # 这里未来可以调用一个轻量级的 LLM (如 DeepSeek-V3) 来做解析
        # 目前先用关键词启发式逻辑作为 Baseline
        intent = {
            "type": "general",
            "entities": [],
            "needs_skills": False,
            "needs_relations": False,
            "needs_history": False,
            "needs_hooks": False
        }
        
        # 简单启发式分析
        low_outline = outline.lower()
        if any(w in low_outline for w in ["打", "战", "杀", "斗", "招式", "伤"]):
            intent["type"] = "combat"
            intent["needs_skills"] = True
        elif any(w in low_outline for w in ["说", "谈", "骂", "争执", "秘密", "心想"]):
            intent["type"] = "dialogue"
            intent["needs_relations"] = True
        elif any(w in low_outline for w in ["发现", "原来", "真相", "线索", "伏笔"]):
            intent["type"] = "revelation"
            intent["needs_hooks"] = True
            
        return intent

    def build_writer_context(self, chapter_num: int, outline: str, active_characters: List[str], scene_location: str, atmosphere: Dict[str, str] = None) -> str:
        """
        重构后的 Writer 上下文构建：意图驱动型检索
        """
        # 0. 意图分析
        intent = self._analyze_plot_intent(outline)
        
        # --- 1. World Bible (绝对真理层) ---
        # 检索逻辑：除了搜大纲，还要显式搜“世界规则”和“地理设定”
        bible_query = f"{scene_location} {outline[:50]}"
        bible_text = self.memory.get_bible_context(query=bible_query, active_entities=active_characters)
        
        current_budget = self.total_budget - self._count_tokens(bible_text)

        # --- 2. Story State (状态层) ---
        # 这一层不检索，直接从数据库取结构化数据
        focus = self.memory.get_narrative_focus()
        active_plan = self.memory.get_active_plan()
        prev_summary = self.memory.get_chapter_summary(chapter_num - 1)
        
        # 动态词表
        vocab_text = self._build_vocabulary_constraints(
            active_plan.get('volume', {}).get('name', '默认'),
            active_plan.get('arc', {}).get('name', '默认')
        )

        # 强制获取活跃伏笔 (不再靠 RAG 碰运气)
        active_hooks = ""
        if intent["needs_hooks"] or intent["type"] == "revelation":
            hooks = self.memory.get_active_foreshadowing()
            if hooks:
                active_hooks = "\n【当前活跃伏笔】:\n" + "\n".join([f"- {h['content']} (ID:{h['id']})" for h in hooks])

        state_text = f"""
# 🌍 宏观状态
【目标】: {focus['goal']}
【当前冲突】: {focus['conflict']}
【卷/单元规划】: {active_plan.get('volume', {}).get('name', '默认')} -> {active_plan.get('arc', {}).get('name', '默认')}
{active_hooks}

# 📜 前情提要
【上一章回顾】: {prev_summary}
"""

        # --- 3. Targeted Retrieval (定向检索层) ---
        # 根据意图分配预算和检索词
        used_tokens = self._count_tokens(state_text)
        retrieval_budget = current_budget - used_tokens
        
        # A. 角色状态 (Mental Ledger & Status)
        # 不再只搜背景，要搜“当前的伤势、心情、持有的道具”
        char_info = "# 👥 角色实时状态\n"
        for char_name in active_characters:
            # 这里的 get_character_details 需要返回结构化的状态栏而非仅仅是简介
            details = self.memory.get_character_details([char_name], query=outline)
            char_info += f"## {char_name}\n{details}\n"
        
        # B. 关系深度检索 (Graph RAG)
        graph_info = ""
        if intent["needs_relations"] or intent["type"] == "dialogue":
            graph_info = "# 🕸️ 社交深度连接\n"
            for char_name in active_characters:
                # 获取 2 度以内的重要关系路径
                graph_info += self.memory.graph.query_entity_context(char_name, current_chapter=chapter_num)
        
        # C. 历史记忆碎片 (Dynamic RAG)
        # 检索策略改进：如果是在战斗，搜“招式、战绩”；如果是文戏，搜“恩怨、对话往来”
        rag_query = f"{' '.join(active_characters)} "
        if intent["type"] == "combat":
            rag_query += f"战斗 招式 伤痕 {outline[:30]}"
        elif intent["type"] == "dialogue":
            rag_query += f"情感 矛盾 承诺 {outline[:30]}"
        else:
            rag_query += outline

        rag_content = self.memory.query_related_context(rag_query, k=10)
        
        # --- 4. Assembly & Trimming ---
        retrieval_text = f"{char_info}\n{graph_info}\n# 🧠 相关记忆碎片\n{rag_content}"
        retrieval_trimmed = self._trim_lines_to_budget(retrieval_text, retrieval_budget)

        # 获取文风样板 (Mapped from Intent)
        style_map = {
            "combat": ["Action", "Scenery"],
            "dialogue": ["Dialogue", "InnerMonologue"],
            "revelation": ["InnerMonologue", "Scenery"],
            "general": ["Scenery", "Dialogue"]
        }
        target_styles = style_map.get(intent["type"], ["Scenery"])
        style_text = self.memory.get_style_examples(tags=target_styles)

        # 格式化氛围要求
        atmosphere_text = ""
        if atmosphere:
            atmosphere_text = f"""
# 🌡️ 本章氛围 (Atmosphere)
- 基调 (Tone): {atmosphere.get('tone', 'N/A')}
- 紧张度 (Tension): {atmosphere.get('tension', 'N/A')}
- 感官侧重 (Sensory): {atmosphere.get('sensory_focus', 'N/A')}
- 环境色调 (Color): {atmosphere.get('color_palette', 'N/A')}
"""

        return f"{bible_text}\n{vocab_text}\n{state_text}\n{atmosphere_text}\n{style_text}\n{retrieval_trimmed}"
