import asyncio
from core.memory import MemoryManager
from core.workflow import NovelWorkflow
from utils.init_world_v2 import init_world_v2

def run_test():
    # 1. Setup Data
    init_world_v2()
    
    memory = MemoryManager()
    workflow = NovelWorkflow(memory)
    app = workflow.build_graph()
    
    # 2. Initial State
    initial_state = {
        "chapter_num": 1,
        "narrative_plan": memory.get_active_plan(),
        "narrative_focus": memory.get_narrative_focus(),
        "outline_data": {},
        "draft_content": "",
        "simulator_feedback": "",
        "simulator_retry_count": 0,
        "review_feedback": "",
        "revision_count": 0,
        "director_ran": False
    }
    
    print("\n🚀 Starting V2 Workflow Test (Chapter 1)...")
    
    # 3. Run
    final_state = app.invoke(initial_state)
    
    # 4. Report
    print("\n✅ Workflow Completed!")
    print(f"Final Content Length: {len(final_state.get('final_content', ''))} chars")
    
    # Check if Simulator triggered
    if final_state.get("simulator_retry_count", 0) > 0:
        print(f"🧠 Simulator intervened {final_state['simulator_retry_count']} times.")
        print(f"Last Feedback: {final_state['simulator_feedback']}")
    else:
        print("🧠 Simulator passed on first try.")

    # Save artifact
    with open("output_chapter_1_v2.txt", "w") as f:
        f.write(final_state.get("final_content", "No Content"))
        
if __name__ == "__main__":
    run_test()

