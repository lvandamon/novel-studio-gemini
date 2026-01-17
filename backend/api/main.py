from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging
import sqlite3
import json
from contextlib import asynccontextmanager

# Import Core Systems
from core.memory import MemoryManager
from core.workflow import NovelWorkflow

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

# Global State
system_state = {
    "memory": None,
    "workflow": None,
    "workflow_app": None
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the heavy AI models on startup"""
    logger.info("🚀 Booting Novel Studio Backend (Stateful Mode)...")
    try:
        system_state["memory"] = MemoryManager()
        system_state["workflow"] = NovelWorkflow(system_state["memory"])
        # Build with persistence
        system_state["workflow_app"] = system_state["workflow"].build_graph(db_path="data/workflow_state.db")
        logger.info("✅ System Ready")
    except Exception as e:
        logger.error(f"❌ Boot failed: {e}")
    yield

app = FastAPI(title="DeepSeek Novel Studio API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models ---

class StartRequest(BaseModel):
    chapter_num: int
    instruction: Optional[str] = None
    force_director: bool = True

class ResumeRequest(BaseModel):
    chapter_num: int
    user_input: Optional[Dict[str, Any]] = None # Input to next node

class StateUpdateRequest(BaseModel):
    chapter_num: int
    state_updates: Dict[str, Any]

class GraphVizRequest(BaseModel):
    center_entity: Optional[str] = None
    depth: int = 2

# --- Helpers ---

def get_thread_config(chapter_num: int):
    return {"configurable": {"thread_id": str(chapter_num)}}

# --- Workflow Endpoints ---

@app.post("/api/workflow/start")
def start_workflow(req: StartRequest):
    """Start (or restart) the workflow for a specific chapter."""
    if not system_state["workflow_app"]:
        raise HTTPException(503, "System not ready")
    
    mem: MemoryManager = system_state["memory"]
    
    # 1. Prepare Initial State
    initial_state = {
        "chapter_num": req.chapter_num,
        "narrative_plan": mem.get_active_plan(),
        "narrative_focus": mem.get_narrative_focus(),
        "revision_count": 0,
        "director_ran": req.force_director,
        "flashback_injection": req.instruction if req.instruction else None,
        # Reset flags
        "requires_director_review": False,
        "high_risk_flag": False,
        "archivist_rejected": False,
        "intervention_reason": None,
        "simulator_feedback": "",
        "review_feedback": ""
    }
    
    config = get_thread_config(req.chapter_num)
    
    # 2. Start Execution (Run until first interrupt)
    try:
        # We use stream to run until the first interruption
        # Since we have interrupt_before=["editor", "writer", "archivist"], 
        # it will likely stop before 'editor' first if Director passes.
        
        # Note: If this is a fresh start, we invoke.
        # But LangGraph invoke with checkpointer will resume if thread exists? 
        # Better to update state and then resume/invoke.
        
        # Let's clean slate for this thread if it exists? 
        # For safety, we just update the state with the new initial values
        system_state["workflow_app"].update_state(config, initial_state)
        
        # Run!
        # This will run until it hits an interrupt node
        for event in system_state["workflow_app"].stream(None, config):
            pass # Just consume stream to execute
            
        return get_workflow_state(req.chapter_num)
        
    except Exception as e:
        logger.error(f"Start failed: {e}")
        raise HTTPException(500, str(e))

@app.get("/api/workflow/{chapter_num}/state")
def get_workflow_state(chapter_num: int):
    """Get the current state of the workflow (where is it paused?)."""
    app_graph = system_state["workflow_app"]
    config = get_thread_config(chapter_num)
    
    try:
        current_state = app_graph.get_state(config)
        if not current_state:
            return {"status": "not_started"}
            
        return {
            "status": "active" if current_state.next else "completed",
            "next_nodes": current_state.next,
            "state_values": current_state.values,
            "created_at": current_state.created_at,
            "config": current_state.config
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/workflow/resume")
def resume_workflow(req: ResumeRequest):
    """Resume execution from the current pause point."""
    app_graph = system_state["workflow_app"]
    config = get_thread_config(req.chapter_num)
    
    try:
        # Run until next interrupt
        # Pass user_input if any (e.g. human feedback)
        input_data = req.user_input if req.user_input else None
        
        for event in app_graph.stream(input_data, config):
            pass
            
        return get_workflow_state(req.chapter_num)
    except Exception as e:
        logger.error(f"Resume failed: {e}")
        raise HTTPException(500, str(e))

@app.post("/api/workflow/update")
def update_workflow_state(req: StateUpdateRequest):
    """
    GOD MODE: Manually inject state updates.
    Use this to edit the 'outline', 'draft_content', or force 'director_ran' flag.
    """
    app_graph = system_state["workflow_app"]
    config = get_thread_config(req.chapter_num)
    
    try:
        # as_node: pretend this update came from the node that just finished or is about to run
        # Usually we just update the state directly.
        app_graph.update_state(config, req.state_updates)
        return {"success": True, "new_state": get_workflow_state(req.chapter_num)}
    except Exception as e:
        raise HTTPException(500, str(e))

# --- Graph Visualization ---

@app.get("/api/graph/visualize")
def visualize_graph(
    limit: int = 100, 
    start_chapter: Optional[int] = None, 
    end_chapter: Optional[int] = None, 
    focus_node: Optional[str] = None
):
    """
    Get Neo4j graph data for frontend visualization.
    Supports filtering by chapter range (Time Slider) and focus entity (Spotlight).
    """
    mem: MemoryManager = system_state["memory"]
    try:
        data = mem.graph.get_visualization_data(
            limit=limit, 
            start_chapter=start_chapter, 
            end_chapter=end_chapter, 
            focus_node=focus_node
        )
        return data
    except Exception as e:
        raise HTTPException(500, f"Graph error: {e}")

@app.get("/api/graph/impact")
def visualize_impact(entity: str):
    """Get the 'Impact Subgraph' for a specific entity."""
    mem: MemoryManager = system_state["memory"]
    try:
        # Get structured impact data
        data = mem.graph.get_impact_subgraph_data(entity)
        return data
    except Exception as e:
        raise HTTPException(500, str(e))

# --- Traditional Data ---

class CharacterUpdateRequest(BaseModel):
    updates: Dict[str, Any]

@app.post("/api/characters/{name}/update")
def update_character(name: str, req: CharacterUpdateRequest):
    """GOD MODE: Manually update character attributes in SQLite."""
    mem: MemoryManager = system_state["memory"]
    try:
        mem.upsert_character(name, req.updates, chapter_num=9999) # 9999 for manual intervention
        return {"success": True, "character": mem.get_character(name)}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/characters")
def list_characters():
    mem: MemoryManager = system_state["memory"]
    return mem.list_characters()

# --- Standard Info ---

@app.get("/api/health")
def health_check():
    return {"status": "ok", "mode": "stateful"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)