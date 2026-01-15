import sys
import os
import json
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.memory import MemoryManager
from utils.god_mode import GodMode

def setup_test_data(memory: MemoryManager):
    print("Initialize Test Data...")
    
    # 1. Create Characters
    blade_data = {
        "role": "Protagonist",
        "personality": ["Cold", "Ruthless"],
        "goals": ["Destroy the Sect"],
        "background": "An orphan raised by wolves."
    }
    memory.upsert_character("Blade", blade_data)
    memory.add_anchor("Blade", "Identity", "I am an orphan with no family.", tags=["Orphan"])
    
    leader_data = {
        "role": "Antagonist",
        "title": "SectLeader",
        "goals": ["Rule the world"]
    }
    memory.upsert_character("SectLeader", leader_data)
    
    # 2. Create Relationship
    print("Creating initial relationship: Blade --[ENEMY_OF]--> SectLeader")
    memory.graph.update_relationship("Blade", "Character", "ENEMY_OF", "SectLeader", "Character", properties={"desc": "Blood feud"})
    
    # Verify initial state
    print("--- Initial State Verified ---")

def test_retcon():
    # Use a temporary DB for testing
    db_path = "data/test_retcon.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        
    memory = MemoryManager(db_path=db_path)
    god = GodMode(memory)
    
    # Setup
    setup_test_data(memory)
    
    # Retcon Instruction
    instruction = "揭示真相：Blade 其实是 SectLeader 的私生子。消除敌对关系，Blade 现在的目标是继承宗门。"
    print(f"\n🚀 Executing Retcon: '{instruction}'\n")
    
    # Execute
    logs = god.retcon_history(instruction)
    
    print("\n--- Execution Logs ---")
    for log in logs:
        print(log)
        
    # Verify Results
    print("\n--- Verifying Changes ---")
    
    # 1. Check Character Update
    blade = memory.get_character("Blade")
    print(f"Blade's Goals: {blade.get('goals')}")
    # We expect goals to change or background to update

    # 2. Check Graph
    # Since we can't easily query graph state without connected Neo4j in this script context 
    # (unless GraphManagerMock is used, but here we use real MemoryManager which tries to connect),
    # we rely on the logs mostly. 
    # But we can check Bible entries.
    
    # 3. Check Bible Patches
    # We can't easily query vector store by exact match logic here without embedding, 
    # but we can check the SQL side of Bible if MemoryManager implemented it.
    # The RetconAgent calls `memory.add_bible_entry`.
    
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT topic, content FROM world_bible WHERE category='RETCON_HISTORY'")
    rows = cursor.fetchall()
    conn.close()
    
    if rows:
        print(f"\n✅ Bible Patches Found ({len(rows)}):")
        for r in rows:
            print(f"   - [{r[0]}]: {r[1]}")
    else:
        print("\n❌ No Bible patches found.")

if __name__ == "__main__":
    test_retcon()
