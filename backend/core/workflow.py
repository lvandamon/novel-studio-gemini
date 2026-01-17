from typing import TypedDict, Literal, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from core.memory import MemoryManager
from core.context_manager import ContextManager
from agents.director_agent import DirectorAgent
from agents.editor_agent import EditorAgent
from agents.simulator_agent import SimulatorAgent
from agents.writer_agent import WriterAgent
from agents.reviewer_agent import ReviewerAgent
from agents.archivist_agent import ArchivistAgent
from agents.reader_agent import ReaderAgent

# --- State Definition ---
class NovelState(TypedDict):
    chapter_num: int

    # Context Data
    narrative_plan: Dict[str, Any]
    narrative_focus: Dict[str, Any]

    # Working Data
    outline_data: Dict[str, Any] # title, outline, characters, etc.
    draft_content: str
    final_content: Optional[str]

    # Feedback Loops
    simulator_feedback: str
    simulator_retry_count: int
    review_feedback: str
    revision_count: int
    reader_feedback: Dict[str, Any] # New: Store reader sentiment

    # Flags
    director_ran: bool
    requires_director_review: bool  # 🔥 P1新增: 标记需要Director特殊审查
    high_risk_flag: bool  # 🔥 P1新增: 标记高风险章节(Simulator多次驳回)
    archivist_rejected: bool # 🔥 P7新增: 档案员逻辑驳回标记
    
    # Intervention
    intervention_reason: Optional[str] # 🔥 P10新增: 人工干预原因
    flashback_injection: Optional[str] # 🔥 P10新增: 用户手动注入的闪回/记忆

from agents.foreshadowing_agent import ForeshadowingAgent

# --- Node Logic ---

class NovelWorkflow:
    def __init__(self, memory: MemoryManager):
        self.memory = memory
        self.context_manager = ContextManager(memory)
        
        # Initialize Agents
        self.director = DirectorAgent(memory)
        self.editor = EditorAgent(self.context_manager)
        self.simulator = SimulatorAgent(memory)
        self.writer = WriterAgent(memory) # 🔥 P1: Pass memory to Writer
        self.reviewer = ReviewerAgent(memory)
        self.reader = ReaderAgent() # Initialize Reader
        self.archivist = ArchivistAgent(memory)
        self.foreshadowing_agent = ForeshadowingAgent(memory)

    def node_director_check(self, state: NovelState) -> NovelState:
        """Node 1: Director Check (Strategic Control)"""
        current_chapter = state["chapter_num"]
        
        # 🔥 P1优化: 动态Director频率
        # 前100章: 每5章 | 100-500章: 每10章 | 500+章: 每15章
        if current_chapter <= 100:
            director_interval = 5
        elif current_chapter <= 500:
            director_interval = 10
        else:
            director_interval = 15

        # Policy: Run Director on interval OR first chapter
        # 🔥 P4: 如果有高风险标记，强制 Director 介入
        high_risk = state.get("high_risk_flag", False)
        
        if current_chapter % director_interval == 0 or current_chapter == 1 or high_risk:
            reason = "高风险阻断" if high_risk else f"周期:{director_interval}章"
            print(f"\n🎥 === Workflow: Director Activation (Ch {current_chapter}, 原因: {reason}) ===")
            
            self.director.evaluate_progress(current_chapter, high_risk_flag=high_risk)
            state["director_ran"] = True
            
            # 如果是高风险触发的，Director 运行后视为已处理（发布了修正指令），重置 flag
            if high_risk:
                state["high_risk_flag"] = False
                print("   ✅ 高风险标记已清除，Director 已接管。")
        else:
            state["director_ran"] = False

        # Refresh context from DB (Director might have changed it)
        state["narrative_plan"] = self.memory.get_active_plan()
        state["narrative_focus"] = self.memory.get_narrative_focus()

        # 🔥 P2新增: 伏笔健康度自动检查(每10章)
        if current_chapter % 10 == 0:
            from agents.foreshadowing_agent import ForeshadowingAgent
            hook_agent = ForeshadowingAgent(self.memory)
            dying_hooks = hook_agent.check_hook_health(current_chapter)
            if dying_hooks:
                print(f"\n⚠️  伏笔健康预警: 发现 {len(dying_hooks)} 个待回收伏笔")
                for hook in dying_hooks[:3]:  # 只显示前3个
                    print(f"   - ID:{hook['id']} (Imp:{hook['importance']}, Gap:{hook['gap']}章) {hook['content'][:30]}...")

        return state

    def node_editor_gen(self, state: NovelState) -> NovelState:
        """Node 2: Editor (Tactical Planning)"""
        print(f"\n📝 === Workflow: Editor Planning ===")
        
        # 1. Build Context
        base_context = self.context_manager.build_director_context(state["chapter_num"])
        roster = self.memory.get_character_roster_brief()
        
        # 2. Extract potential characters for Causal Lookup
        # 策略：从 Narrative Focus 的 goal、上一章摘要、以及【伏笔建议】中提取提到的角色
        focus = state.get("narrative_focus", {})
        prev_summary = self.memory.get_chapter_summary(state["chapter_num"] - 1)
        
        # 🆕 获取伏笔建议并从中提取角色
        hook_suggestions = self.foreshadowing_agent.suggest_callbacks(state["chapter_num"], current_location=None)
        
        # 合并所有文本进行实体提取
        search_text = f"{focus.get('goal', '')} {prev_summary} {hook_suggestions}"
        potential_chars = self.memory._extract_entities_semantically(search_text)
        
        # 获取这些角色的因果上下文 (包括从第一卷到现在的恩怨)
        causal_context = self.editor._get_causal_context(potential_chars)

        # 🆕 核心修复：注入之前的驳回反馈，防止无效重试循环
        rejection_context = ""
        sim_feedback = state.get("simulator_feedback", "")
        if sim_feedback and "PASS" not in sim_feedback:
            rejection_context += f"\n\n🛑【逻辑沙盘驳回】(上一次规划失败的原因):\n{sim_feedback}\n"
            
        # 如果是因为档案员发现历史冲突回滚的
        if state.get("archivist_rejected"):
             rejection_context += f"\n\n🚨【历史一致性致命冲突】(档案员发现本剧情违背了历史设定):\n{state.get('review_feedback', '未知冲突')}\n"

        full_context = f"""
{base_context}

## 5. 角色分布 (Roster)
{roster}

## 6. 伏笔回收建议 (Callbacks - Priority)
{hook_suggestions}
{rejection_context}
"""

        outline_data = self.editor.generate_outline(state["chapter_num"], full_context, causal_context=causal_context)

        # 🔥 P2新增: 自动检测大纲是否隐含伏笔回收
        outline_str = "\n".join(outline_data.get("outline", []))
        potential_resolutions = self.foreshadowing_agent.detect_outline_resolutions(outline_str)
        if potential_resolutions:
            print(f"   🔍 检测到大纲可能回收伏笔: {potential_resolutions}")
            outline_data["potential_hook_resolutions"] = potential_resolutions

        state["outline_data"] = outline_data
        return state

    def node_simulator_check(self, state: NovelState) -> NovelState:
        """Node 2.5: Simulator (Character Logic Sandbox)"""
        print(f"\n🧠 === Workflow: Simulator Check ===")
        
        outline_data = state["outline_data"]
        active_chars = outline_data.get("active_characters", [])
        
        if not active_chars:
            print("   ⚠️ 无活跃角色，跳过模拟。")
            state["simulator_feedback"] = "PASS"
            return state
            
        result = self.simulator.simulate_outline(outline_data, active_chars)
        
        if result.get("status") == "REJECT":
            state["simulator_feedback"] = f"【模拟器驳回】: {result.get('conflict_analysis')}\n【修改建议】: {result.get('suggestion')}"
        else:
            state["simulator_feedback"] = "PASS"
            
        state["simulator_retry_count"] = state.get("simulator_retry_count", 0) + 1
        return state

    def node_writer_gen(self, state: NovelState) -> NovelState:
        """Node 3: Writer (Execution)"""
        print(f"\n✍️ === Workflow: Writer Drafting (Rev {state.get('revision_count', 0)}) ===")
        
        outline_data = state["outline_data"]
        outline_str = "\n".join(outline_data.get("outline", []))
        active_chars = outline_data.get("active_characters", [])
        scene_loc = outline_data.get("scene_location", "未知")
        atmosphere = outline_data.get("atmosphere", {})
        
        # Use ContextManager to build the sophisticated, budget-aware context
        context_package = self.context_manager.build_writer_context(
            chapter_num=state["chapter_num"],
            outline=outline_str,
            active_characters=active_chars,
            scene_location=scene_loc,
            atmosphere=atmosphere,
            flashback_injection=state.get("flashback_injection") # 🔥 P10: Inject User Flashback
        )
        
        # Add review feedback if re-drafting (only if NOT passed)
        review_raw = state.get("review_feedback", "")
        if review_raw and "PASS" not in review_raw:
            try:
                import json
                fb_data = json.loads(review_raw)
                # 只有当状态不是 APPROVED/PASS 时才注入
                if fb_data.get("status") != "PASS":
                    suggestion = fb_data.get("suggestion", review_raw)
                    context_package += f"\n\n🛑【导演/审核驳回指令】(必须修正):\n{suggestion}\n"
            except:
                context_package += f"\n\n⚠️【必须修正的问题】(来自上一轮审核):\n{review_raw}\n"
        
        draft = self.writer.write_chapter(outline_str, context_package, active_characters=active_chars)
        state["draft_content"] = draft
        return state

    def node_reviewer_check(self, state: NovelState) -> NovelState:
        """Node 4: Reviewer (Quality Control)"""
        print(f"\n🧐 === Workflow: Reviewer Checking ===")
        outline_data = state.get("outline_data", {})
        active_chars = outline_data.get("active_characters", [])
        
        feedback = self.reviewer.review_draft(state["draft_content"], chapter_num=state["chapter_num"], active_characters=active_chars)
        state["review_feedback"] = feedback
        
        state["revision_count"] = state.get("revision_count", 0) + 1
        return state

    def node_reader_eval(self, state: NovelState) -> NovelState:
        """Node 4.5: Reader (Sentiment Analysis)"""
        print(f"\n👀 === Workflow: Reader Reading ===")
        feedback = self.reader.read_chapter(state["draft_content"])
        state["reader_feedback"] = feedback
        return state

    def node_archivist_save(self, state: NovelState) -> NovelState:
        """Node 5: Archivist (Persistence)"""
        print(f"\n🗄️ === Workflow: Archiving ===")
        import json
        
        try:
            # 1. 基础归档 (Fact Extraction)
            # 🔥 P7修正: 捕捉 Archivist 的 ValueError (逻辑冲突)
            self.archivist.archive_chapter(state["draft_content"], state["chapter_num"])
            
            # 2. 深度伏笔分析 (Clue Hunting)
            self.foreshadowing_agent.analyze_hooks(state["draft_content"], state["chapter_num"])
            
            # 🆕 3. 同步读者指标到遥测数据库
            reader_fb = state.get("reader_feedback", {})
            if reader_fb:
                metrics = {
                    "reader_boredom": reader_fb.get("boredom_score", 50),
                    "reader_expectation": reader_fb.get("expectation_score", 50),
                    "critique": f"Reader Comment: {reader_fb.get('comment', '')}"
                }
                # 注意：这里是更新已有记录（Reviewer已经创建了基础记录）
                self.memory.log_chapter_metrics(state["chapter_num"], metrics)
                print(f"   📊 读者遥测数据已同步: Boredom={metrics['reader_boredom']}")

            # Append Reader Feedback to final text for human reading
            fb_str = f"\n\n--- 📊 读者反馈报告 ---\nMood: {reader_fb.get('reader_mood')}\nBoredom: {reader_fb.get('boredom_score')}\nExpectation: {reader_fb.get('expectation_score')}\nComment: {reader_fb.get('comment')}\n"
            
            state["final_content"] = state["draft_content"] + fb_str
            state["archivist_rejected"] = False
            
        except ValueError as e:
            print(f"   🛑 Archivist 拒绝归档: {e}")
            # 构造反馈给 Editor/Writer
            err_msg = str(e)
            state["review_feedback"] = json.dumps({
                "status": "BLOCK",
                "suggestion": f"【历史一致性致命错误】档案员拒绝归档。原因：\n{err_msg}\n请修改剧情以符合历史设定，或联系导演进行RETCON。"
            }, ensure_ascii=False)
            state["archivist_rejected"] = True
            
        return state

    # --- Edge Logic ---

    def check_archivist_status(self, state: NovelState) -> Literal["approved", "rejected"]:
        if state.get("archivist_rejected"):
            return "rejected"
        return "approved"

    def check_simulator_status(self, state: NovelState) -> Literal["approve", "reject", "intervention"]:
        feedback = state.get("simulator_feedback", "")
        retries = state.get("simulator_retry_count", 0)

        if "PASS" in feedback:
            return "approve"

        # 🔥 P1修复: 优化重试逻辑
        if retries >= 3:
            print("   🚨 模拟器驳回次数过多(3次)，触发强制人工干预流程 (Human-in-the-Loop)。")
            print(f"   📋 驳回理由: {feedback}")
            
            # 标记干预原因
            state["intervention_reason"] = f"模拟器连续驳回3次，逻辑死锁。\n最后反馈: {feedback}"
            return "intervention"

        print(f"   🔙 模拟器驳回(尝试 {retries}/3)，Editor 重写大纲...")
        return "reject"

    def check_review_status(self, state: NovelState) -> Literal["approve", "reject"]:
        import json
        feedback_raw = state.get("review_feedback", "")
        revisions = state.get("revision_count", 0)
        
        try:
            feedback_data = json.loads(feedback_raw)
        except:
            # Fallback for legacy string format or error
            if "PASS" in feedback_raw: return "approve"
            return "reject"
            
        status = feedback_data.get("status", "BLOCK")
        metrics = feedback_data.get("metrics", {})
        
        # --- DIRECTOR'S ROLLBACK AUTHORITY (熔断机制) ---
        # 即使 Status 是 PASS，如果核心指标过低，强制驳回
        logic_score = metrics.get("plot_logic_score", 100)
        alignment_score = metrics.get("alignment_score", 100) # Director's Will
        
        threshold = 80 # 严格标准
        
        if revisions >= 3:
            print("   ⚠️ 达到最大修改次数 (3)，强制通过（即使有瑕疵）。")
            return "approve"

        if status == "BLOCK":
            print(f"   ❌ Reviewer 明确驳回: {feedback_data.get('suggestion')}")
            return "reject"
            
        if logic_score < threshold:
            print(f"   🛡️ 逻辑熔断 (Logic {logic_score} < {threshold}) -> 强制回滚！")
            # 注入新的修改建议
            feedback_data["suggestion"] = f"【系统强制驳回】逻辑分过低 ({logic_score})。请检查硬逻辑冲突。"
            state["review_feedback"] = json.dumps(feedback_data, ensure_ascii=False)
            return "reject"

        if alignment_score < threshold:
            print(f"   🎬 导演回滚 (Alignment {alignment_score} < {threshold}) -> 严重偏离叙事焦点！")
             # 注入新的修改建议
            feedback_data["suggestion"] = f"【导演强制驳回】你写偏了！({alignment_score})。请严格遵循 Narrative Focus (Goal/Beat)。"
            state["review_feedback"] = json.dumps(feedback_data, ensure_ascii=False)
            return "reject"
            
        print(f"   ✅ 审核通过 (Logic: {logic_score}, Alignment: {alignment_score})")
        return "approve"

    def build_graph(self, db_path: str = "data/workflow_state.db", enable_interrupts: bool = True):
        from langgraph.checkpoint.sqlite import SqliteSaver
        import sqlite3

        # Setup Checkpointer DB connection
        conn = sqlite3.connect(db_path, check_same_thread=False)
        memory_saver = SqliteSaver(conn)

        workflow = StateGraph(NovelState)
        
        # Add Nodes
        workflow.add_node("director", self.node_director_check)
        workflow.add_node("editor", self.node_editor_gen)
        workflow.add_node("simulator", self.node_simulator_check)
        workflow.add_node("writer", self.node_writer_gen)
        workflow.add_node("reviewer", self.node_reviewer_check)
        workflow.add_node("reader", self.node_reader_eval) # Add Reader Node
        workflow.add_node("archivist", self.node_archivist_save)
        
        # Add Edges
        workflow.set_entry_point("director")
        workflow.add_edge("director", "editor")
        workflow.add_edge("editor", "simulator")
        
        # Conditional Edge: Simulator -> Writer (Pass) OR Editor (Reject)
        workflow.add_conditional_edges(
            "simulator",
            self.check_simulator_status,
            {
                "approve": "writer",
                "reject": "editor",
                "intervention": END  # Stop workflow for human intervention
            }
        )
        
        workflow.add_edge("writer", "reviewer")
        
        # Conditional Edge: Reviewer -> Reader (Pass) OR Writer (Reject)
        workflow.add_conditional_edges(
            "reviewer",
            self.check_review_status,
            {
                "approve": "reader", # Pass to Reader instead of Archivist
                "reject": "writer"
            }
        )
        
        workflow.add_edge("reader", "archivist") # Reader -> Archivist
        
        # 🔥 P7修正: Archivist 驳回逻辑闭环
        workflow.add_conditional_edges(
            "archivist",
            self.check_archivist_status,
            {
                "approved": END,
                "rejected": "editor" # 严重历史冲突，打回 Editor 重构大纲
            }
        )
        
        # Compile with Checkpointer and Interrupt Logic
        # interrupt_before: 在进入这些节点前暂停，允许人类修改 State
        interrupts = ["editor", "writer", "archivist"] if enable_interrupts else []
        return workflow.compile(
            checkpointer=memory_saver,
            interrupt_before=interrupts 
        )