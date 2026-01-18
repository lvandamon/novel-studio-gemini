import sys
import os
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent.parent))

from core.world_consistency import WorldConsistencyEngine
from unittest.mock import MagicMock

def test_economy_violation():
    print("🧪 Testing Economy Violation...")
    mock_memory = MagicMock()
    engine = WorldConsistencyEngine(mock_memory)
    
    # 正常内容
    safe_draft = "主角走进茶馆，掏出两文钱买了一个热腾腾的烧饼。"
    violations = engine.validate_economy(safe_draft, ["主角"])
    assert len(violations) == 0, "Safe draft should have no violations"
    print("✅ Safe draft passed.")

    # 离谱内容: 100两金子买烧饼
    crazy_draft = "主角极其阔绰，随手甩出一百两金子，只为了买一个路边的破烧饼。"
    violations = engine.validate_economy(crazy_draft, ["主角"])
    assert len(violations) > 0, "Crazy draft should be caught!"
    print(f"✅ Caught violation: {violations[0]['detail']}")

if __name__ == "__main__":
    test_economy_violation()
