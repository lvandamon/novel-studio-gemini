import tiktoken
from typing import List, Dict, Any, Optional
from core.memory import MemoryManager
from core.physics import PhysicalityEngine
import json
from langchain_core.output_parsers import StrOutputParser
from core.llm import get_deepseek_chat
from core.prompts import CONTEXT_INTENT_PROMPT, CONTEXT_COMPRESSION_PROMPT
import re

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
        self.physics_engine = PhysicalityEngine(self.memory)
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
        
        # 初始化 LLM 链
        self.llm = get_deepseek_chat(temperature=0.1) 
        self.intent_chain = CONTEXT_INTENT_PROMPT | self.llm | StrOutputParser()
        self.compressor_chain = CONTEXT_COMPRESSION_PROMPT | self.llm | StrOutputParser()

    def _count_tokens(self, text: str) -> int:
        return len(self.encoder.encode(text))

    def _trim_lines_to_budget(self, text: str, budget: int, from_start: bool = True) -> str:
        """按行裁剪文本以适应 token 预算 (Physical Fallback)"""
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

    def _smart_fit(self, content: str, budget: int) -> str:
        """
        智能适配预算 (Smart Compression Strategy)
        1. 计算当前 token 数。
        2. 如果超标，调用 LLM 进行语义压缩 (Semantic Compression)。
        3. 如果压缩后依然超标 (罕见)，执行物理裁剪 (Physical Trimming) 作为兜底。
        """
        current_usage = self._count_tokens(content)
        if current_usage <= budget:
            return content
            
        print(f"   🤏 Context Overflow ({current_usage} > {budget}). Triggering Semantic Compression...")
        
        try:
            # 尝试压缩
            compressed_content = self.compressor_chain.invoke({
                "content": content,
                "budget": budget
            })
            
            new_usage = self._count_tokens(compressed_content)
            print(f"   -> Compressed to {new_usage} tokens.")
            
            # 如果依然超标，进行物理裁剪
            if new_usage > budget:
                print("   ⚠️ Compression insufficient. Applying physical trim fallback.")
                return self._trim_lines_to_budget(compressed_content, budget)
                
            return compressed_content
            
        except Exception as e:
            print(f"   ⚠️ Compression Failed: {e}. Fallback to trim.")
            return self._trim_lines_to_budget(content, budget)

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
        [核心逻辑升级] AI 意图解析器
        使用 DeepSeek-V3 快速分析情节意图，返回结构化检索指令。
        """
        print("   🧠 正在解析本章叙事意图...")
        try:
            response = self.intent_chain.invoke({"outline": outline})
            
            # 清理可能的 markdown 包裹
            clean_json = response.strip()
            if "```json" in clean_json:
                clean_json = re.search(r'```json\s*(\{.*\})\s*```', clean_json, re.DOTALL).group(1)
            elif "```" in clean_json:
                clean_json = clean_json.replace("```", "")
                
            intent_data = json.loads(clean_json)
            # 简单的验证，确保字段存在
            required_fields = ["type", "needs_skills", "needs_relations", "needs_history", "needs_hooks", "needs_world_rules"]
            for field in required_fields:
                if field not in intent_data:
                    intent_data[field] = False # Default fallback
            
            print(f"   👉 意图识别: [{intent_data.get('type')}] - 需要技能:{intent_data.get('needs_skills')} | 需要关系:{intent_data.get('needs_relations')}")
            return intent_data
            
        except Exception as e:
            print(f"   ⚠️ 意图解析失败，回退到基础模式: {e}")
            # Fallback heuristic
            intent = {
                "type": "General",
                "needs_skills": False,
                "needs_relations": False,
                "needs_history": False,
                "needs_hooks": False,
                "needs_world_rules": False
            }
            low_outline = outline.lower()
            if any(w in low_outline for w in ["打", "战", "杀", "斗", "招式", "伤"]):
                intent["type"] = "Combat"
                intent["needs_skills"] = True
            elif any(w in low_outline for w in ["说", "谈", "骂", "争执", "秘密", "心想"]):
                intent["type"] = "Social"
                intent["needs_relations"] = True
                
            return intent

    def build_writer_context(self, chapter_num: int, outline: str, active_characters: List[str], scene_location: str, atmosphere: Dict[str, str] = None) -> str:
        """
        重构后的 Writer 上下文构建：意图驱动型检索 + 智能压缩
        """
        # 0. 意图分析
        intent = self._analyze_plot_intent(outline)
        
        # --- 1. World Bible (绝对真理层 - 不可压缩) ---
        bible_query = f"{scene_location}"
        if intent.get('needs_world_rules') or intent.get('needs_skills'):
             bible_query += f" {outline[:100]} 功法 境界 规则"
        else:
             bible_query += f" {outline[:50]}"
             
        bible_text = self.memory.get_bible_context(query=bible_query, active_entities=active_characters)
        
        # --- 1.5. Physicality Engine (物理法则层 - 不可压缩) ---
        physics_text = self.physics_engine.get_hard_constraints_for_prompt(active_characters, scene_location)
        
        current_budget = self.total_budget - self._count_tokens(bible_text) - self._count_tokens(physics_text)

        # --- 2. Story State (状态层 - 必须保留，但可轻度压缩) ---
        focus = self.memory.get_narrative_focus()
        active_plan = self.memory.get_active_plan()
        prev_summary = self.memory.get_chapter_summary(chapter_num - 1)
        
        vocab_text = self._build_vocabulary_constraints(
            active_plan.get('volume', {}).get('name', '默认'),
            active_plan.get('arc', {}).get('name', '默认')
        )

        active_hooks = ""
        if intent["needs_hooks"] or intent["type"] == "Investigation":
            hooks = self.memory.get_active_foreshadowing()
            if hooks:
                active_hooks = "\n【当前活跃伏笔 (需重点关注)】:\n" + "\n".join([f"- {h['content']} (ID:{h['id']})" for h in hooks])

        state_text = f"""
# 🌍 宏观状态
【目标】: {focus['goal']}
【当前冲突】: {focus['conflict']}
【卷/单元规划】: {active_plan.get('volume', {}).get('name', '默认')} -> {active_plan.get('arc', {}).get('name', '默认')}
{active_hooks}

# 📜 前情提要
【上一章回顾】: {prev_summary}
"""
        
        # 计算剩余预算
        used_tokens = self._count_tokens(state_text) + self._count_tokens(vocab_text)
        retrieval_budget = current_budget - used_tokens
        # 确保至少有 2000 tokens 给检索，否则报错或强行分配
        if retrieval_budget < 2000:
             retrieval_budget = 2000 

        # --- 3. Targeted Retrieval (定向检索层 - 智能压缩区) ---
        
        # A. 角色状态
        char_info = "# 👥 角色实时状态\n"
        for char_name in active_characters:
            details = self.memory.get_character_details([char_name], query=outline)
            char_info += f"## {char_name}\n{details}\n"
        
        # B. 关系深度检索 (Subgraph Extraction)
        graph_info = ""
        if intent["needs_relations"] or intent["type"] == "Social" or len(active_characters) > 1:
            graph_info = self.memory.graph.get_multi_entity_relationships(active_characters)
        else:
            # 单人场景或无复杂关系，只查简单的邻居
            for char_name in active_characters:
                 neighbors = self.memory.graph.query_entity_context(char_name, current_chapter=chapter_num)
                 if "暂无" not in neighbors:
                     graph_info += f"## {char_name} 的周边关系\n{neighbors}\n"
        
        # C. 历史记忆碎片
        rag_query = f"{ ' '.join(active_characters)} "
        if intent["type"] == "Combat":
            rag_query += f"战斗 招式 伤痕 弱点 {outline[:50]}"
        elif intent["type"] == "Social":
            rag_query += f"情感 矛盾 承诺 谎言 {outline[:50]}"
        elif intent["type"] == "Investigation":
            rag_query += f"线索 秘密 历史 真相 {outline[:50]}"
        elif intent["type"] == "Introspection":
            rag_query += f"心魔 执念 悟道 {outline[:50]}"
        else:
            rag_query += outline

        if intent.get("needs_history"):
            rag_query += " 往事 历史"

        # 动态增加 k 值，获取更多原始素材供压缩
        rag_content = self.memory.query_related_context(rag_query, k=15 if intent["needs_history"] else 10, current_chapter=chapter_num)
        
        # --- 4. Smart Fit (智能适配) ---
        retrieval_text_raw = f"{char_info}\n{graph_info}\n# 🧠 相关记忆碎片 (基于意图:{intent['type']})\n{rag_content}"
        
        # 调用智能压缩
        retrieval_optimized = self._smart_fit(retrieval_text_raw, retrieval_budget)

        # 获取文风样板
        style_map = {
            "Combat": ["Action", "Scenery"],
            "Social": ["Dialogue", "InnerMonologue"],
            "Investigation": ["InnerMonologue", "Scenery"],
            "Introspection": ["InnerMonologue", "Philosophy"],
            "Travel": ["Scenery"],
            "General": ["Scenery", "Dialogue"]
        }
        target_styles = style_map.get(intent["type"], ["Scenery"])
        style_text = self.memory.get_style_examples(tags=target_styles)

        # 格式化氛围
        atmosphere_text = ""
        if atmosphere:
            atmosphere_text = f"""
# 🌡️ 本章氛围 (Atmosphere)
- 基调 (Tone): {atmosphere.get('tone', 'N/A')}
- 紧张度 (Tension): {atmosphere.get('tension', 'N/A')}
- 感官侧重 (Sensory): {atmosphere.get('sensory_focus', 'N/A')}
- 环境色调 (Color): {atmosphere.get('color_palette', 'N/A')}
"""

        return f"{bible_text}\n{physics_text}\n{vocab_text}\n{state_text}\n{atmosphere_text}\n{style_text}\n{retrieval_optimized}"