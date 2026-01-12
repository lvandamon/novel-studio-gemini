from core.memory import MemoryManager
from core.physics import PhysicalityEngine
from core.schemas import BodyPartStatus, StatusEffect, InventoryItem
import shutil
import os

# Clean up previous test data
if os.path.exists("data/test_refactor_db"):
    shutil.rmtree("data/test_refactor_db")

# Init
mem = MemoryManager(db_path="data/test_refactor_db/novel.db", vector_db_path="data/test_refactor_db/vec")
phys = PhysicalityEngine(mem)

# 1. Create a character with LEGACY data (simulate old db)
print("--- Test 1: Legacy Data Migration ---")
mem.upsert_character("Xiao Feng", {
    "level": "Qi Condensation 3",
    "inventory": ["Iron Sword", "Healing Pill"] # Old string list
})

char = mem.get_character("Xiao Feng")
print(f"Legacy Inventory: {char['inventory']}")

# 2. Update with NEW Hard Logic data (Simulate a severe battle)
print("\n--- Test 2: Hard Logic Update ---")
new_data = {
    "body_status": [
        BodyPartStatus(name="Left Arm", is_severed=True, health=0).model_dump(),
        BodyPartStatus(name="Meridians", health=30, notes="Damaged by fire").model_dump()
    ],
    "active_effects": [
        StatusEffect(name="Fire Poison", description="Burning pain", intensity=3, duration_chapters=5).model_dump()
    ],
    "inventory": [
        InventoryItem(name="Iron Sword", durability=0, status="Broken").model_dump(), # Broken sword
        InventoryItem(name="Mysterious Ring", category="Artifact").model_dump()      # New item
    ]
}
mem.upsert_character("Xiao Feng", new_data)

# 3. Verify Prompt Generation
print("\n--- Test 3: Prompt Output (Writer View) ---")
prompt = phys.get_hard_constraints_for_prompt(["Xiao Feng"], "Wilderness")
print(prompt)

# Check for critical keywords
assert "Left Arm" in prompt
assert "❌缺失" in prompt or "SEVERED" in prompt
assert "Fire Poison" in prompt
assert "💔已损毁" in prompt

print("\n✅ All Refactoring Checks Passed!")