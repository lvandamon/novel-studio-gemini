
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.workflow import NovelWorkflow
from core.memory import MemoryManager
from utils.init_world_v2 import init_world_v2
from utils.init_style import init_style_data
import time

def run_stress_test(start_chapter=1, end_chapter=10):
    print(f"🚀 === Starting Stress Test (Ch{start_chapter} -> Ch{end_chapter}) ===")
    
    # 1. Initialize
    db_path = "data/novel_stress_test.db"
    vec_path = "data/vector_stress_test"
    
    # Clean previous test data if starting from 1
    if start_chapter == 1:
        if os.path.exists(db_path): os.remove(db_path)
        import shutil
        if os.path.exists(vec_path): shutil.rmtree(vec_path)
        if os.path.exists("novel_output"): shutil.rmtree("novel_output")
        os.makedirs("novel_output", exist_ok=True)
    
    # Init Memory & World
    memory = MemoryManager(db_path=db_path, vector_db_path=vec_path)
    
    if start_chapter == 1:
        print("🌍 Initializing World Bible & Style...")
        # Hack: The init scripts usually instantiate their own MemoryManager. 
        # We need to make sure they use OUR db_path.
        # But looking at the code, they use default args. 
        # Let's temporarily monkey-patch or just copy the logic.
        # Actually, simpler way: Just call them, but we need to ensure they target novel_stress_test.db
        # Since the utils don't accept db_path args easily without refactoring, 
        # let's just use the default DB 'data/novel.db' for simplicity in this stress test, 
        # OR better, let's manually init data using our memory object here.
        
        # Manual Init based on logic from utils (since we can't easily pass db_path to them)
        # Actually, init_world_v2 uses default MemoryManager(). 
        # Let's trust the user wants to run on 'data/novel.db' for now or refactor utils.
        # WAIT: The prompt said "stress_test_loop.py". I should stick to the requested structure.
        # To avoid polluting main DB, I'll update the MemoryManager init in the script 
        # to use the default paths IF I can't change utils.
        # But wait, I can just modify the imports.
        
        # Let's Try: We will modify the MemoryManager instantiation in utils via arguments? No.
        # Okay, for this test run, let's just use the DEFAULT db path to avoid complexity, 
        # or accepting that we might pollute 'data/novel.db' is a bad idea.
        
        # Better strategy: Monkey patch MemoryManager default args? No.
        # Real Strategy: The previous `stress_test_loop.py` defined specific paths.
        # Let's stick to specific paths and replicate the init logic manually here 
        # OR just instantiate the util functions if they allow passing memory.
        # Checking `init_world_v2`: it does `memory = MemoryManager()`. Hardcoded.
        # Checking `init_style_data`: it does `memory = MemoryManager()`. Hardcoded.
        
        # So I cannot reuse them directly with custom DB paths without refactoring them.
        # SOLUTION: I will use the DEFAULT DB paths for this stress test to ensure it works 
        # with the existing utils. I will warn the user.
        pass

    # RE-INITIALIZING with ISOLATED paths
    db_path = "data/novel_stress_test.db" 
    vec_path = "data/vector_stress_test"
    
    # Clean previous test data if starting from 1
    if start_chapter == 1:
        if os.path.exists(db_path): os.remove(db_path)
        import shutil
        if os.path.exists(vec_path): shutil.rmtree(vec_path)
        if os.path.exists("novel_output"): shutil.rmtree("novel_output")
        os.makedirs("novel_output", exist_ok=True)

    memory = MemoryManager(db_path=db_path, vector_db_path=vec_path)
    
    if start_chapter == 1:
        print("🌍 Initializing World Bible & Style (Isolated Env)...")
        init_world_v2(memory) 
        init_style_data(memory)
    
    workflow = NovelWorkflow(memory)
    app = workflow.build_graph()
    
    # 2. Loop
    for i in range(start_chapter, end_chapter + 1):
        print(f"\n\n⚡️⚡️⚡️ [STRESS TEST] Processing Chapter {i} ⚡️⚡️⚡️")
        start_time = time.time()
        
        # Initial State
        state = {
            "chapter_num": i,
            "revision_count": 0,
            "director_ran": False
        }
        
        # Run Workflow
        try:
            final_state = app.invoke(state)
            
            # 3. Validation & Telemetry
            duration = time.time() - start_time
            
            # Fetch metrics
            conn = memory._get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT tension, character_consistency_score, plot_logic_score FROM chapter_metrics WHERE chapter_num = ?', (i,))
            row = cursor.fetchone()
            conn.close()
            
            metrics_str = "N/A"
            if row:
                metrics_str = f"Tension={row[0]}, Consistency={row[1]}, Logic={row[2]}"
            
            print(f"✅ Chapter {i} Completed in {duration:.1f}s")
            print(f"📊 Telemetry: {metrics_str}")
            
            # Verify File Output
            file_path = f"novel_output/Chapter_{i:04d}.md"
            if os.path.exists(file_path):
                size = os.path.getsize(file_path)
                print(f"💾 File Saved: {file_path} ({size} bytes)")
            else:
                print(f"❌ CRITICAL: File NOT found at {file_path}")
                
        except Exception as e:
            print(f"❌ CRITICAL ERROR at Chapter {i}: {e}")
            import traceback
            traceback.print_exc()
            break

if __name__ == "__main__":
    # You can adjust the range here
    run_stress_test(start_chapter=1, end_chapter=5)
