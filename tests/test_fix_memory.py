import pytest
import shutil
import os
from core.memory import MemoryManager

TEST_DB = "data/test_fix_memory.db"
TEST_VEC = "data/test_fix_vec"

@pytest.fixture
def memory():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    if os.path.exists(TEST_VEC):
        shutil.rmtree(TEST_VEC)
    
    mm = MemoryManager(db_path=TEST_DB, vector_db_path=TEST_VEC)
    yield mm
    
    # Cleanup
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    if os.path.exists(TEST_VEC):
        shutil.rmtree(TEST_VEC)

def test_personality_overwrite(memory):
    # 1. Initial State
    memory.upsert_character("Alice", {
        "personality": ["Brave", "Kind"],
        "level": "Level 1"
    })
    
    char = memory.get_character("Alice")
    assert set(char["personality"]) == {"Brave", "Kind"}
    
    # 2. Update with new personality (Should Overwrite)
    memory.upsert_character("Alice", {
        "personality": ["Cruel", "Dark"], # Changed completely
        "level": "Level 2"
    })
    
    char = memory.get_character("Alice")
    # Verify Overwrite behavior
    assert "Brave" not in char["personality"]
    assert "Kind" not in char["personality"]
    assert set(char["personality"]) == {"Cruel", "Dark"}
    
    # 3. Update without personality (Should keep existing)
    memory.upsert_character("Alice", {
        "level": "Level 3"
    })
    char = memory.get_character("Alice")
    assert set(char["personality"]) == {"Cruel", "Dark"}

def test_inventory_removal(memory):
    # 1. Initial Inventory
    memory.upsert_character("Bob", {
        "inventory": ["Sword", "Shield", "Potion"]
    })
    
    char = memory.get_character("Bob")
    assert set(char["inventory"]) == {"Sword", "Shield", "Potion"}
    
    # 2. Consume Potion (Use removed_items)
    memory.upsert_character("Bob", {
        "inventory": ["Map"], # Found a map
        "removed_items": ["Potion"] # Drank potion
    })
    
    char = memory.get_character("Bob")
    current_inv = set(char["inventory"])
    assert "Potion" not in current_inv
    assert "Sword" in current_inv # Kept
    assert "Shield" in current_inv # Kept
    assert "Map" in current_inv # Added

def test_mixed_list_behavior(memory):
    # Verify other lists still merge
    memory.upsert_character("Charlie", {
        "aliases": ["Chuck"]
    })
    
    memory.upsert_character("Charlie", {
        "aliases": ["Charles"]
    })
    
    char = memory.get_character("Charlie")
    assert set(char["aliases"]) == {"Charlie", "Chuck", "Charles"} # Name is always an alias too
