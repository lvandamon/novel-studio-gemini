from typing import TypedDict, Literal, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from core.memory import MemoryManager
from agents.director_agent import DirectorAgent
from agents.editor_agent import EditorAgent
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
    review_feedback: str
    revision_count: int
    
    # Flags
    director_ran: bool

# --- Node Logic ---

class NovelWorkflow:
    def __init__(self, memory: MemoryManager):
        self.memory = memory
        
        # Initialize Agents
        self.director = DirectorAgent(memory)
        self.editor = EditorAgent()
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
        
        # Prepare Context Package for Editor
        # (Editor needs to know available characters at the location, current beat, etc.)
        focus = state["narrative_focus"]
        plan = state["narrative_plan"]
        
        # Get brief roster (Editor needs global view)
        roster = self.memory.get_character_roster_brief()
        
        context_str = f"""
        【当前规划】: Vol: {plan.get('volume', {}).get('name')} / Arc: {plan.get('arc', {}).get('name')}
        【叙事焦点】: Beat: {focus.get('beat')} | Goal: {focus.get('goal')} | Conflict: {focus.get('conflict')}
        【世界状态】: {focus.get('state')}
        【现有角色分布】:
        {roster}
        """
        
        outline_data = self.editor.generate_outline(context_str, state["chapter_num"])
        state["outline_data"] = outline_data
        return state

    def node_writer_gen(self, state: NovelState) -> NovelState:
        """Node 3: Writer (Execution)"""
        print(f"\n✍️ === Workflow: Writer Drafting (Rev {state.get('revision_count', 0)}) ===")
        
        outline = state["outline_data"].get("outline", "（无大纲）")
        scene_location = state["outline_data"].get("scene_location", "未知")
        active_chars = state["outline_data"].get("active_characters", [])
        
        # Prepare Writer's Context Package (Local View)
        # 1. Local Roster (Who is here?)
        local_roster = self.memory.get_local_roster(scene_location)
        
        # 2. Character Details (Deep dive for active chars)
        char_details = self.memory.get_character_details(active_chars)
        
        # 3. Feedback (If revision)
        feedback_context = ""
        if state.get("review_feedback"):
            feedback_context = f"\n⚠️【必须修正的问题】(来自上一轮审核):\n{state['review_feedback']}\n请针对上述问题重写本章。"

        context_package = f"""
        【场景地点】: {scene_location}
        【在场人员】:
        {local_roster}
        
        【重点角色详情】:
        {char_details}
        
        {feedback_context}
        """
        
        draft = self.writer.write_chapter(outline, context_package)
        state["draft_content"] = draft
        return state

    def node_reviewer_check(self, state: NovelState) -> NovelState:
        """Node 4: Reviewer (Quality Control)"""
        print(f"\n🧐 === Workflow: Reviewer Checking ===")
        feedback = self.reviewer.review_draft(state["draft_content"])
        state["review_feedback"] = feedback
        
        # Increment revision count
        state["revision_count"] = state.get("revision_count", 0) + 1
        return state

    def node_archivist_save(self, state: NovelState) -> NovelState:
        """Node 5: Archivist (Persistence)"""
        print(f"\n🗄️ === Workflow: Archiving ===")
        self.archivist.archive_chapter(state["draft_content"], state["chapter_num"])
        state["final_content"] = state["draft_content"]
        return state

    # --- Edge Logic ---

    def check_review_status(self, state: NovelState) -> Literal["approve", "reject"]:
        feedback = state.get("review_feedback", "")
        revisions = state.get("revision_count", 0)
        
        # Pass condition: Explicit "PASS" or max revisions reached
        if "PASS" in feedback:
            print("   ✅ 审核通过！")
            return "approve"
        
        if revisions >= 2:
            print("   ⚠️ 达到最大修改次数，强制通过（保留瑕疵）。")
            return "approve" # Force pass to avoid infinite loop
            
        print("   ❌ 审核未通过，发回重修。")
        return "reject"

    def build_graph(self):
        workflow = StateGraph(NovelState)
        
        # Add Nodes
        workflow.add_node("director", self.node_director_check)
        workflow.add_node("editor", self.node_editor_gen)
        workflow.add_node("writer", self.node_writer_gen)
        workflow.add_node("reviewer", self.node_reviewer_check)
        workflow.add_node("archivist", self.node_archivist_save)
        
        # Add Edges
        workflow.set_entry_point("director")
        workflow.add_edge("director", "editor")
        workflow.add_edge("editor", "writer")
        workflow.add_edge("writer", "reviewer")
        
        # Conditional Edge
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
