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
    
    # Flags
    director_ran: bool

# --- Node Logic ---

class NovelWorkflow:
    def __init__(self, memory: MemoryManager):
        self.memory = memory
        self.context_manager = ContextManager(memory)
        
        # Initialize Agents
        self.director = DirectorAgent(memory)
        self.editor = EditorAgent(self.context_manager)
        self.simulator = SimulatorAgent(memory)
        self.writer = WriterAgent()
        self.reviewer = ReviewerAgent(memory)
        self.archivist = ArchivistAgent(memory)

    def node_director_check(self, state: NovelState) -> NovelState:
        """Node 1: Director Check (Strategic Control)"""
        current_chapter = state["chapter_num"]
        
        # Policy: Run Director every 5 chapters OR first chapter
        if current_chapter % 5 == 0 or current_chapter == 1:
            print(f"\n🎥 === Workflow: Director Activation (Ch {current_chapter}) ===")
            self.director.evaluate_progress(current_chapter)
            state["director_ran"] = True
        else:
            state["director_ran"] = False
            
        # Refresh context from DB (Director might have changed it)
        state["narrative_plan"] = self.memory.get_active_plan()
        state["narrative_focus"] = self.memory.get_narrative_focus()
        
        return state

    def node_editor_gen(self, state: NovelState) -> NovelState:
        """Node 2: Editor (Tactical Planning)"""
        print(f"\n📝 === Workflow: Editor Planning ===")
        
        # 1. Build Context
        # Editor 既需要宏观把控（Director Context），也需要全局花名册（Roster）
        base_context = self.context_manager.build_director_context(state["chapter_num"])
        roster = self.memory.get_character_roster_brief()
        
        full_context = f"""
{base_context}

## 5. 角色分布 (Roster)
{roster}

## 6. 上一轮模拟反馈 (如果有)
{state.get('simulator_feedback', '无')}
"""
        
        outline_data = self.editor.generate_outline(full_context, state["chapter_num"])
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
            atmosphere=atmosphere
        )
        
        # Add review feedback if re-drafting
        if state.get("review_feedback"):
            context_package += f"\n\n⚠️【必须修正的问题】(来自上一轮审核):\n{state['review_feedback']}\n"
        
        draft = self.writer.write_chapter(outline_str, context_package)
        state["draft_content"] = draft
        return state

    def node_reviewer_check(self, state: NovelState) -> NovelState:
        """Node 4: Reviewer (Quality Control)"""
        print(f"\n🧐 === Workflow: Reviewer Checking ===")
        outline_data = state.get("outline_data", {})
        active_chars = outline_data.get("active_characters", [])
        
        feedback = self.reviewer.review_draft(state["draft_content"], active_characters=active_chars)
        state["review_feedback"] = feedback
        
        state["revision_count"] = state.get("revision_count", 0) + 1
        return state

    def node_archivist_save(self, state: NovelState) -> NovelState:
        """Node 5: Archivist (Persistence)"""
        print(f"\n🗄️ === Workflow: Archiving ===")
        self.archivist.archive_chapter(state["draft_content"], state["chapter_num"])
        state["final_content"] = state["draft_content"]
        return state

    # --- Edge Logic ---

    def check_simulator_status(self, state: NovelState) -> Literal["approve", "reject"]:
        feedback = state.get("simulator_feedback", "")
        retries = state.get("simulator_retry_count", 0)
        
        if "PASS" in feedback:
            return "approve"
        
        if retries >= 3:
            print("   ⚠️ 模拟器驳回次数过多，强制通过（此时应由人类介入）。")
            return "approve"
            
        print("   🔙 模拟器驳回，Editor 重写大纲...")
        return "reject"

    def check_review_status(self, state: NovelState) -> Literal["approve", "reject"]:
        feedback = state.get("review_feedback", "")
        revisions = state.get("revision_count", 0)
        
        if "PASS" in feedback:
            print("   ✅ 审核通过！")
            return "approve"
        
        if revisions >= 2:
            print("   ⚠️ 达到最大修改次数，强制通过（保留瑕疵）。")
            return "approve" 
            
        print("   ❌ 审核未通过，发回重修。")
        return "reject"

    def build_graph(self):
        workflow = StateGraph(NovelState)
        
        # Add Nodes
        workflow.add_node("director", self.node_director_check)
        workflow.add_node("editor", self.node_editor_gen)
        workflow.add_node("simulator", self.node_simulator_check)
        workflow.add_node("writer", self.node_writer_gen)
        workflow.add_node("reviewer", self.node_reviewer_check)
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
                "reject": "editor"
            }
        )
        
        workflow.add_edge("writer", "reviewer")
        
        # Conditional Edge: Reviewer -> Archivist (Pass) OR Writer (Reject)
        workflow.add_conditional_edges(
            "reviewer",
            self.check_review_status,
            {
                "approve": "archivist",
                "reject": "writer"
            }
        )
        
        workflow.add_edge("archivist", END)
        
        return workflow.compile()