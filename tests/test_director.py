import pytest
import shutil
import os
import json
from unittest.mock import MagicMock, patch
from core.memory import MemoryManager
from agents.director_agent import DirectorAgent

TEST_DB = "data/test_director.db"
TEST_VEC = "data/test_director_vec"

@pytest.fixture
def memory():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    if os.path.exists(TEST_VEC):
        shutil.rmtree(TEST_VEC)
    
    mm = MemoryManager(db_path=TEST_DB, vector_db_path=TEST_VEC)
    
    # Setup initial state
    mm.create_volume("Volume 1", "Rise of the Hero", "Establish protagonist")
    mm.create_arc(1, "Academy Arc", "Learn basics", "Win tournament", ["Meeting rival", "First fight"], start_chapter=1)
    mm.activate_arc(1, 1)
    
    # Mock some chapter summaries (dragging plot)
    mm.update_chapter_summary(1, "Xiao Feng enters the academy.")
    mm.update_chapter_summary(2, "Xiao Feng eats lunch.")
    mm.update_chapter_summary(3, "Xiao Feng sleeps.")
    mm.update_chapter_summary(4, "Xiao Feng looks at the sky.")
    mm.update_chapter_summary(5, "Xiao Feng sighs.")
    
    yield mm
    
    # Cleanup
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    if os.path.exists(TEST_VEC):
        shutil.rmtree(TEST_VEC)

@pytest.fixture
def director(memory):
    return DirectorAgent(memory)

def test_director_evaluation(director):
    # Mock LLM response to avoid API calls and ensure deterministic testing
    mock_response = """
    ```json
    {
        "analysis": "The plot is extremely slow. 5 chapters of doing nothing.",
        "pacing_directive": "Accelerate",
        "narrative_focus_update": {
            "current_beat": "Inciting Incident",
            "current_goal": "Force a conflict",
            "current_conflict": "Rival attacks",
            "world_state_summary": "Tension rising"
        },
        "should_end_arc": false,
        "global_event": "Headmaster announces tournament",
        "critique": "Boring."
    }
    ```
    """
    
    # Replace the chain with a MagicMock to avoid Pydantic/LangChain patching issues
    director.chain = MagicMock()
    director.chain.invoke.return_value = mock_response

    decision = director.evaluate_progress(current_chapter=5)
    
    # Verify result structure
    assert decision["pacing_directive"] == "Accelerate"
    assert decision["should_end_arc"] is False
    assert decision["global_event"] == "Headmaster announces tournament"
    
    # Verify Side Effects (DB Updates)
    focus = director.memory.get_narrative_focus()
    assert focus["beat"] == "Inciting Incident"
    assert focus["conflict"] == "Rival attacks"
    
    # Verify Global Event Logged
    events = director.memory.get_relevant_events("WORLD", recent_k=1)
    assert "Headmaster announces tournament" in events
