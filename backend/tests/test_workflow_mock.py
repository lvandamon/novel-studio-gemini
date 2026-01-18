import pytest
import shutil
import os
from unittest.mock import MagicMock
from core.memory import MemoryManager
from core.workflow import NovelWorkflow

TEST_DB = "data/test_flow.db"
TEST_VEC = "data/test_flow_vec"

@pytest.fixture
def workflow():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    if os.path.exists(TEST_VEC):
        shutil.rmtree(TEST_VEC)
    
    mm = MemoryManager(db_path=TEST_DB, vector_db_path=TEST_VEC)
    
    # Init basic data
    mm.create_volume("Vol 1", "Test Vol", "Test Goal")
    mm.create_arc(1, "Arc 1", "Test Arc", "Test Goal", ["Event A"], start_chapter=1)
    mm.activate_arc(1, 1)
    mm.update_narrative_focus("Vol 1", "Arc 1", "Start", "Goal", "Conflict", "State")
    
    wf = NovelWorkflow(mm)
    
    # Mock Agents to avoid API calls
    wf.director.evaluate_progress = MagicMock()
    wf.editor.generate_outline = MagicMock(return_value={
        "outline": "Chapter 1 Outline", 
        "active_characters": ["Alice"],
        "scene_location": "School"
    })
    wf.writer.write_chapter = MagicMock(return_value="This is Chapter 1 text.")
    wf.reviewer.review_draft = MagicMock(return_value="PASS")
    wf.archivist.archive_chapter = MagicMock()
    wf.simulator.simulate_outline = MagicMock(return_value={"status": "PASS"}) # 🔥 Mock Simulator
    wf.polisher.polish_draft = MagicMock(side_effect=lambda draft, outline: draft) # Pass-through
    wf.reader.read_chapter = MagicMock(return_value={
        "boredom_score": 10, 
        "expectation_score": 90, 
        "reader_mood": "Excited", 
        "comment": "Good", 
        "highlight": "None"
    })
    
    yield wf
    
    # Cleanup
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    if os.path.exists(TEST_VEC):
        shutil.rmtree(TEST_VEC)

def test_full_workflow_happy_path(workflow):
    # Prepare initial state
    initial_state = {
        "chapter_num": 1,
        "narrative_plan": {},
        "narrative_focus": {},
        "revision_count": 0
    }
    
    # Run graph
    app = workflow.build_graph(enable_interrupts=False)
    config = {"configurable": {"thread_id": "test_thread_1"}}
    result = app.invoke(initial_state, config)
    
    # Verify sequence
    workflow.director.evaluate_progress.assert_called_once() # Ch 1 triggers director
    workflow.editor.generate_outline.assert_called_once()
    workflow.writer.write_chapter.assert_called_once()
    workflow.reviewer.review_draft.assert_called_once()
    workflow.archivist.archive_chapter.assert_called_once()
    
    assert result["draft_content"] == "This is Chapter 1 text."
    assert "This is Chapter 1 text." in result["final_content"]

def test_workflow_revision_loop(workflow):
    # Mock Reviewer to fail once then pass
    workflow.reviewer.review_draft = MagicMock(side_effect=["Fail: Too short", "PASS"])
    
    initial_state = {
        "chapter_num": 2, # Not 1 or 5, so Director skipped
        "narrative_plan": {},
        "narrative_focus": {},
        "revision_count": 0
    }
    
    app = workflow.build_graph(enable_interrupts=False)
    config = {"configurable": {"thread_id": "test_thread_2"}}
    result = app.invoke(initial_state, config)
    
    # Verify Director skipped
    workflow.director.evaluate_progress.assert_not_called()
    
    # Verify Writer called twice (1 initial + 1 revision)
    assert workflow.writer.write_chapter.call_count == 2
    assert workflow.reviewer.review_draft.call_count == 2
    
    # Verify Archiver called only once at the end
    workflow.archivist.archive_chapter.assert_called_once()
