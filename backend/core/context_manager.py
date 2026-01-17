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
    分层级上下文管理器 (Hierarchical Context Manager) - 200万字增强版
    
    层级结构：
    1. Global Layer (世界层): 终极目标、世界规则、当前卷/单元规划。 (Cacheable)
    2. Local Layer (场景层): 当前场景位置、在场角色(Roster)、上一章摘要。 (Dynamic)
    3. Retrieval Layer (检索层): 针对当前情节大纲(Outline)动态检索的事件、伏笔、图谱。 (Highly Dynamic)
    
    新增特性:
    - 动态预算 (Dynamic Budgeting): 根据章节数自适应扩容
    - 纹理检索 (Texture Retrieval): 检索高光时刻，防止文风干瘪
    - 创伤注入 (Trauma Injection): 自动注入角色深层心理创伤
    """
    
    def __init__(self, memory_manager: MemoryManager, model_name: str = "gpt-4o"):
        self.memory = memory_manager
        self.physics_engine = PhysicalityEngine(self.memory)
        try:
            self.encoder = tiktoken.encoding_for_model(model_name)
        except:
            self.encoder = tiktoken.get_encoding("cl100k_base")

        # 🔥 P1升级: 动态预算系统
        self.base_total_budget = 64000
        self.max_total_budget = 96000
        self.total_budget = self.base_total_budget

        # 缓存配置
        self._cache = {
            "world_bible": {"content": None, "chapter": -1},
            "volume_plan": {"content": None, "volume_id": None},
            "vocabulary": {"content": None, "arc_name": None}
        }

        # 关键信息保护标记
        self.critical_markers = {
            "anchors": ("⚓️", "⚓️END"),
            "physics": ("⚙️", "⚙️END"),
            "core_hook": ("‼️", "‼️END"),
            "director": ("🎬", "🎬END"),
        }

        self.llm = get_deepseek_chat(temperature=0.1)
        self.intent_chain = CONTEXT_INTENT_PROMPT | self.llm | StrOutputParser()
        self.compressor_chain = CONTEXT_COMPRESSION_PROMPT | self.llm | StrOutputParser()

    def _count_tokens(self, text: str) -> int:
        return len(self.encoder.encode(text))

    def _analyze_plot_intent(self, outline: str) -> Dict[str, Any]:
        """AI 意图解析器"""
        try:
            response = self.intent_chain.invoke({"outline": outline})
            # Clean json
            clean = response.strip()
            if "```" in clean:
                clean = re.search(r'```json\s*(\{.*\})\s*```', clean, re.DOTALL).group(1)
            return json.loads(clean)
        except:
            return {"type": "General", "needs_history": True, "needs_hooks": True, "needs_relations": True, "needs_world_rules": True}

    def _semantic_compression(self, content: str, budget: int) -> str:
        """
        🔥 P8升级: 语义压缩引擎 (Semantic Compression Engine)
        不再粗暴截断，而是使用 LLM 对非核心信息进行高密度摘要。
        """
        current_tokens = self._count_tokens(content)
        if current_tokens <= budget:
            return content

        print(f"   🤏 Context Compression Triggered: {current_tokens} -> Target {budget}")
        
        # 尝试使用 LLM 压缩
        try:
            compressed = self.compressor_chain.invoke({
                "content": content,
                "budget": budget
            })
            
            # Double check
            if self._count_tokens(compressed) > budget * 1.2:
                # If still too large, force truncate the *compressed* version (less lossy than truncating raw)
                return self._force_truncate(compressed, budget)
                
            return f"=== 🧠 压缩记忆上下文 (Compressed Memory) ===\n{compressed}"
        except Exception as e:
            print(f"   ⚠️ Compression Failed: {e}, falling back to truncation.")
            return self._force_truncate(content, budget)

    def _force_truncate(self, content: str, budget: int) -> str:
        """最后手段：硬截断"""
        lines = content.split('\n')
        kept = []
        curr = 0
        for line in lines:
            t = self._count_tokens(line)
            if curr + t > budget: break
            kept.append(line)
            curr += t
        return "\n".join(kept) + "\n(Context Truncated by System Limit)"

    def build_director_context(self, chapter_num: int) -> str:
        """为 Director 提供宏观视角"""
        focus = self.memory.get_narrative_focus()
        active_plan = self.memory.get_active_plan()
        
        bible_text = self.memory.get_bible_context(query=focus['goal'])
        
        progress_text = f"当前进度: 第 {chapter_num} 章\n"
        if active_plan["volume"]:
            progress_text += f"卷: {active_plan['volume']['name']} (目标: {active_plan['volume']['goal']})\n"
        
        focus_text = f"""
当前节拍: {focus['beat']}
当前冲突: {focus['conflict']}
世界状态: {focus['state']}
"""
        # 活跃伏笔
        hooks = self.memory.get_active_foreshadowing()
        hooks_text = "\n".join([f"- [ID:{h['id']}] {h['content']}" for h in hooks]) if hooks else "无活跃伏笔"

        # 近期摘要
        summaries = self.memory.get_recent_aggregated_summaries(level="chapter", limit=10) # Using chapter summaries
        # Or better:
        summaries = []
        for i in range(max(1, chapter_num - 10), chapter_num):
            s = self.memory.get_chapter_summary(i)
            summaries.append(f"Ch{i}: {s}")
        recent_history = "\n".join(summaries)

        return f"""
{bible_text}
# 🎬 导演控制台
## 1. 宏观进度
{progress_text}## 2. 叙事状态
{focus_text}## 3. 待处理伏笔
{hooks_text}## 4. 近期剧情
{recent_history}
"""
    
    def build_editor_context(self, chapter_num: int, prev_summary: str) -> str:
        """Editor Context Wrapper"""
        return self.build_director_context(chapter_num) + f"\n\n## 上一章回顾\n{prev_summary}"

    def build_writer_context(self, chapter_num: int, outline: str, active_characters: List[str], scene_location: str, atmosphere: Dict[str, str] = None, flashback_injection: str = None) -> str:
        """
        Writer 上下文构建：意图驱动 + 纹理注入 + 创伤映射 + 迷雾系统
        """
        # 0. 意图分析
        intent = self._analyze_plot_intent(outline)
        
        # 1. World Bible & Physics & Ledger (不可压缩层)
        bible_query = f"{scene_location} {outline[:100]}"
        bible_text = self.memory.get_bible_context(query=bible_query, active_entities=active_characters)
        physics_text = self.physics_engine.get_hard_constraints_for_prompt(active_characters, scene_location)
        ledger_text = self.memory.get_full_ledger_context(active_characters)
        
        current_budget = self.total_budget - self._count_tokens(bible_text) - self._count_tokens(physics_text) - self._count_tokens(ledger_text)
        
        # 2. Story State & Hooks
        focus = self.memory.get_narrative_focus()
        active_plan = self.memory.get_active_plan()
        prev_summary = self.memory.get_chapter_summary(chapter_num - 1)
        
        # Hooks selection
        all_hooks = self.memory.get_active_foreshadowing()
        stale_hooks = self.memory.get_stale_unresolved_hooks(limit=3) # 🔥 P6: Force inject old hooks
        
        hook_lines = []
        
        # 1. Stale Hooks (强制提醒)
        if stale_hooks:
            hook_lines.append("‼️ [必须填坑/回扣] 以下伏笔已埋藏很久，请尝试推进或解决：")
            for h in stale_hooks:
                hook_lines.append(f"   - (自Ch{h['chapter_created']}) {h['content']}")
        
        # 2. Active/Recent Hooks
        for h in all_hooks:
            # 避免重复
            if any(sh['id'] == h['id'] for sh in stale_hooks):
                continue
                
            if h.get('importance', 5) >= 8:
                hook_lines.append(f"‼️ [核心悬念] {h['content']}")
            elif intent["needs_hooks"]:
                hook_lines.append(f"- [线索] {h['content']}")
                
        active_hooks = "\n".join(hook_lines)

        state_text = f"""
# 🌍 宏观状态
【目标】: {focus['goal']}
【冲突】: {focus['conflict']}
【规划】: {active_plan.get('volume', {}).get('name')} -> {active_plan.get('arc', {}).get('name')}
{active_hooks}
# 📜 前情提要
{prev_summary}
"""
        
        # 3. Director Instruction
        pacing = focus.get('pacing', 'Normal')
        director_instruction = f"# 🎬 导演指令\n【节奏】: {pacing}"
        
        # 🔥 POV & Fog of War Constraint
        pov_char = active_characters[0] if active_characters else "上帝视角"
        pov_constraint = f"""
# 👁️ 视角限制 (Fog of War)
【当前POV角色】: {pov_char}
⚠️ 严禁开启全知视角！你只能描写 {pov_char} 能看到、听到、感知到的信息。
对于其他角色的心理活动，除非 {pov_char} 有读心术，否则只能通过表情和动作来侧面推测。
"""
        
        used = self._count_tokens(state_text) + self._count_tokens(director_instruction) + self._count_tokens(pov_constraint)
        retrieval_budget = max(4000, current_budget - used) # 保证至少有4k给检索
        
        # 4. Retrieval Layer (角色+关系+记忆)
        char_info = "# 👥 角色状态\n"
        for char_name in active_characters:
            # Anchor + Trauma (Implicitly included in anchors text via DynamicAnchorManager)
            anchors = self.memory.get_character_anchors(char_name)
            if anchors:
                char_info += f"## {char_name}\n{anchors}\n\n"
            
            details = self.memory.get_character_details([char_name], query=outline)
            char_info += f"{details}\n"

        # Relationships
        graph_info = ""
        if len(active_characters) > 1 or intent["needs_relations"]:
            graph_info = self.memory.graph.get_multi_entity_relationships(active_characters, current_chapter=chapter_num)

        # RAG Memory
        rag_query = f"{ ' '.join(active_characters)} {outline}"
        rag_content = self.memory.query_related_context(rag_query, k=10, current_chapter=chapter_num)
        
        # 🔥 P5: Texture Retrieval (高光纹理注入)
        texture_text = ""
        if intent.get("needs_history") or intent.get("type") in ["Social", "Introspection", "Combat"]:
            # 检索与当前意图相关的感官描写
            highlights = self.memory.retrieve_highlights(f"{outline} {intent['type']}", k=3)
            if highlights:
                texture_text = f"\n{highlights}\n"

        # User Flashback
        user_flashback = ""
        if flashback_injection:
            user_flashback = f"\n‼️[强制记忆注入]\n{flashback_injection}\n"

        # Atmosphere
        atm_text = ""
        if atmosphere:
            atm_text = f"\n# 🌡️ 氛围: {atmosphere.get('tone')} | Tension: {atmosphere.get('tension')}\n"

        # Smart Fit with Semantic Compression
        retrieval_raw = f"{char_info}\n{graph_info}\n# 🧠 记忆碎片\n{rag_content}"
        retrieval_optimized = self._semantic_compression(retrieval_raw, retrieval_budget)
        
        return f"{bible_text}\n{physics_text}\n{ledger_text}\n{state_text}\n{director_instruction}\n{pov_constraint}\n{atm_text}\n{texture_text}\n{user_flashback}\n{retrieval_optimized}"