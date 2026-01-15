from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging
import sqlite3
import json
import os
import pandas as pd
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
    "workflow_app": None,
    "is_generating": False,
    "last_error": None
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the heavy AI models on startup"""
    logger.info("🚀 Booting Novel Studio Backend...")
    try:
        system_state["memory"] = MemoryManager()
        system_state["workflow"] = NovelWorkflow(system_state["memory"])
        system_state["workflow_app"] = system_state["workflow"].build_graph()
        logger.info("✅ System Ready")
    except Exception as e:
        logger.error(f"❌ Boot failed: {e}")
    yield
    # Cleanup if needed

app = FastAPI(title="DeepSeek Novel Studio API", lifespan=lifespan)

# CORS (Allow Frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, lock this down
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models ---

class GenerateRequest(BaseModel):
    instruction: str
    flashback: Optional[str] = None
    force_director: bool = True

class ChapterUpdate(BaseModel):
    content: str

class ChapterInfo(BaseModel):
    chapter_num: int
    title: Optional[str]
    summary: Optional[str]
    content: Optional[str]

# --- Endpoints ---

@app.get("/api/health")
def health_check():
    return {"status": "ok", "ready": system_state["memory"] is not None}

@app.get("/api/state")
def get_current_state():
    """Get the 'Head' of the novel (next chapter info)"""
    if not system_state["memory"]:
        raise HTTPException(status_code=503, detail="System initializing")
    
    mem: MemoryManager = system_state["memory"]
    
    # Get Max Chapter
    try:
        conn = sqlite3.connect(mem.db_path)
        cur = conn.cursor()
        cur.execute("SELECT MAX(chapter_num) FROM chapters")
        row = cur.fetchone()
        last_chap = row[0] if row and row[0] else 0
        conn.close()
    except:
        last_chap = 0

    next_chap = last_chap + 1
    
    return {
        "current_chapter": next_chap,
        "last_chapter": last_chap,
        "is_generating": system_state["is_generating"],
        "focus": mem.get_narrative_focus(),
        "active_plan": mem.get_active_plan()
    }

@app.post("/api/generate")
def generate_chapter_endpoint(req: GenerateRequest):
    """Trigger the LangGraph Workflow"""
    if system_state["is_generating"]:
        raise HTTPException(status_code=409, detail="Already generating")
    
    if not system_state["workflow_app"]:
        raise HTTPException(status_code=503, detail="System not ready")

    system_state["is_generating"] = True
    mem: MemoryManager = system_state["memory"]
    
    # Calculate Next Chapter
    # (Simplified: assume we always write the next sequential chapter)
    try:
        conn = sqlite3.connect(mem.db_path)
        cur = conn.cursor()
        cur.execute("SELECT MAX(chapter_num) FROM chapters")
        row = cur.fetchone()
        next_chap = (row[0] + 1) if row and row[0] else 1
        conn.close()
    except:
        next_chap = 1

    # Prepare Input State
    initial_state = {
        "chapter_num": next_chap,
        "narrative_plan": mem.get_active_plan(),
        "narrative_focus": mem.get_narrative_focus(),
        "revision_count": 0,
        "director_ran": req.force_director,
        "flashback_injection": req.instruction if req.instruction else None
    }
    
    try:
        # Run blocking (for now)
        logger.info(f"🎬 Starting generation for Ch.{next_chap} with instruction: {req.instruction}")
        result = system_state["workflow_app"].invoke(initial_state)
        
        system_state["is_generating"] = False
        
        if result.get("final_content"):
            return {
                "success": True, 
                "chapter_num": next_chap,
                "content": result.get("final_content"),
                "logs": ["Generation Complete"] # We need better logging strategy later
            }
        else:
            return {
                "success": False,
                "error": result.get("intervention_reason", "Unknown error")
            }
            
    except Exception as e:
        system_state["is_generating"] = False
        logger.error(f"Generate failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chapters/{chapter_num}")
def get_chapter(chapter_num: int):
    mem: MemoryManager = system_state["memory"]
    if not mem:
        raise HTTPException(503)
        
    try:
        conn = sqlite3.connect(mem.db_path)
        cur = conn.cursor()
        cur.execute("SELECT title, summary, content FROM chapters WHERE chapter_num = ?", (chapter_num,))
        row = cur.fetchone()
        conn.close()
        
        if row:
            return {"chapter_num": chapter_num, "title": row[0], "summary": row[1], "content": row[2]}
        else:
            raise HTTPException(404, detail="Chapter not found")
    except Exception as e:
        raise HTTPException(500, detail=str(e))

@app.put("/api/chapters/{chapter_num}")
def update_chapter(chapter_num: int, update: ChapterUpdate):
    mem: MemoryManager = system_state["memory"]
    try:
        conn = sqlite3.connect(mem.db_path)
        cur = conn.cursor()
        cur.execute("UPDATE chapters SET content = ? WHERE chapter_num = ?", (update.content, chapter_num))
        conn.commit()
        conn.close()
        return {"success": True}
    except Exception as e:
        raise HTTPException(500, detail=str(e))

@app.get("/api/characters")
def list_characters():
    mem: MemoryManager = system_state["memory"]
    try:
        conn = sqlite3.connect(mem.db_path)
        df = pd.read_sql("SELECT id, name, data FROM characters", conn) # Requires pandas
        conn.close()
        
        chars = []
        for _, row in df.iterrows():
            d = json.loads(row['data'])
            chars.append({
                "id": row['id'],
                "name": row['name'],
                "role": d.get("role", "NPC"),
                "state": d.get("current_state", "Normal")
            })
        return chars
    except Exception as e:
        # Fallback if pandas not imported inside function, though it is global in memory.py? 
        # Actually memory.py imports pandas. But main.py needs it if we use it here.
        # Let's use pure sqlite3 to be safe
        conn = sqlite3.connect(mem.db_path)
        cur = conn.cursor()
        cur.execute("SELECT id, name, data FROM characters")
        rows = cur.fetchall()
        conn.close()
        
        chars = []
        for r in rows:
            try:
                d = json.loads(r[2])
                chars.append({
                    "id": r[0],
                    "name": r[1],
                    "role": d.get("role", "NPC"),
                    "state": d.get("current_state", "Unknown")
                })
            except:
                pass
        return chars

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
