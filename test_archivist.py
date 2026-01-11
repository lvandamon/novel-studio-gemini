import os
import shutil
from dotenv import load_dotenv
from core.memory import MemoryManager
from agents.archivist_agent import ArchivistAgent
import json
import sqlite3

def test_full_archivist_capabilities():
    load_dotenv()
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("Skipping test: No API Key")
        return

    print("--- Testing Archivist Full Capabilities (Voice + Time + Resilience) ---")
    
    # Setup
    test_dir = "data/test_archivist_full"
    db_path = f"{test_dir}/novel.db"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    
    memory = MemoryManager(db_path=db_path, vector_db_path=f"{test_dir}/vector_store")
    archivist = ArchivistAgent(memory)
    
    # Set initial date
    print("📅 Setting initial date to: 天道历元年1月1日")
    memory.update_world_date("天道历元年1月1日")
    
    # Mock Chapter Content with Time Passage and Dialogue
    content = """
    第11章 闭关修炼
    
    解决掉赵猛后，萧风回到了破败的柴房。
    “这点实力还远远不够。”他低声自语，眼中闪过一丝狠厉。
    
    他从怀中取出那枚从赵猛身上搜来的下品灵石，盘膝坐下。
    “希望能助我突破练气四层。”
    
    ......
    
    修炼无岁月。转眼间，三天过去了。
    
    柴房的门被推开，清晨的阳光洒在萧风脸上。他缓缓睁开双眼，吐出一口浊气。
    “终于...突破了。”
    """
    
    # Execute
    print("⏳ Archiving chapter...")
    try:
        archivist.archive_chapter(content, 11)
    except Exception as e:
        print(f"❌ Archive failed with error: {e}")
        return

    # Verify Character Voice
    print("\n--- Verifying Character Voice ---")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT data FROM characters WHERE name='萧风'")
    row = cursor.fetchone()
    
    if row:
        data = json.loads(row[0])
        print(f"Name: {data.get('name')}")
        print(f"Dialogue Style: {data.get('dialogue_style', 'N/A')}")
        print(f"Dialogue Examples: {data.get('dialogue_examples', [])}")
        
        if data.get('dialogue_examples'):
             print("✅ Voice Extraction: PASS")
        else:
             print("❌ Voice Extraction: FAIL")
    else:
        print("❌ Character not found.")

    # Verify Time Passage
    print("\n--- Verifying Time Passage ---")
    cursor.execute("SELECT current_date FROM narrative_focus WHERE id=1")
    row = cursor.fetchone()
    conn.close()
    
    if row:
        new_date = row[0]
        print(f"Initial Date: 天道历元年1月1日")
        print(f"New Date: {new_date}")
        
        # Simple string check (LLM format might vary slightly)
        if "1月4日" in new_date or "一月四日" in new_date:
            print("✅ Time Calculation: PASS")
        elif new_date != "天道历元年1月1日":
            print(f"⚠️ Time Changed but format verification needs manual check: {new_date}")
        else:
            print("❌ Time Calculation: FAIL (Date did not change)")
    else:
        print("❌ Narrative Focus not found.")

    # Cleanup
    # shutil.rmtree(test_dir) 

if __name__ == "__main__":
    test_full_archivist_capabilities()
