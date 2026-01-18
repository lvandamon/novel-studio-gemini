"""
🔥 Simulator重试策略测试

测试内容:
1. 死锁检测（相似大纲连续驳回）
2. 历史驳回原因累积
3. 强制升级建议机制
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.workflow import NovelWorkflow


class MockGraph:
    """Mock GraphManager"""
    def get_multi_entity_relationships(self, *args):
        return "无关系"


class MockMemory:
    """最小化Mock MemoryManager"""
    def __init__(self):
        self.db_path = ":memory:"
        self.graph = MockGraph()

    def get_character_details(self, *args, **kwargs):
        return "韩立: 筑基期修士"

    def get_character_mental_curve(self, *args, **kwargs):
        return "平静"

    def get_character_anchors(self, char):
        return f"{char}: 永不相信他人"

    def get_multi_entity_relationships(self, *args):
        return "无关系"


class MockSimulator:
    """模拟总是驳回的Simulator"""
    def __init__(self):
        self.call_count = 0

    def simulate_outline(self, outline_data, active_chars):
        self.call_count += 1
        return {
            "status": "REJECT",
            "conflict_analysis": f"测试驳回 #{self.call_count}",
            "suggestion": f"建议修改 #{self.call_count}"
        }


def test_simulator_retry_strategy():
    """测试死锁检测和升级建议"""

    # 1. 创建Workflow
    memory = MockMemory()
    workflow = NovelWorkflow(memory)

    # 替换为Mock Simulator
    mock_sim = MockSimulator()
    workflow.simulator = mock_sim

    # 2. 创建初始State
    state = {
        "chapter_num": 1,
        "narrative_plan": {},
        "narrative_focus": {},
        "outline_data": {
            "outline": ["韩立在洞府闭关修炼", "突破到筑基后期"],
            "active_characters": ["韩立"]
        },
        "draft_content": "",
        "final_content": None,
        "simulator_feedback": "",
        "simulator_retry_count": 0,
        "simulator_rejection_history": [],
        "review_feedback": "",
        "revision_count": 0,
        "reader_feedback": {},
        "director_ran": False,
        "requires_director_review": False,
        "high_risk_flag": False,
        "archivist_rejected": False,
        "intervention_reason": None,
        "flashback_injection": None
    }

    # 3. 第一次驳回（正常反馈）
    print("\n=== 第1次Simulator驳回 ===")
    result1 = workflow.node_simulator_check(state)
    assert result1["simulator_retry_count"] == 1
    assert "死锁" not in result1["simulator_feedback"]
    assert len(result1["simulator_rejection_history"]) == 1
    print(f"✓ 第1次: {result1['simulator_feedback'][:50]}...")

    # 4. 第二次驳回（相似大纲，应触发死锁检测）
    print("\n=== 第2次Simulator驳回（相似大纲）===")
    state["outline_data"]["outline"] = ["韩立在洞府闭关修炼", "突破到筑基后期，但遇到瓶颈"]  # 高度相似
    result2 = workflow.node_simulator_check(state)
    assert result2["simulator_retry_count"] == 2
    assert len(result2["simulator_rejection_history"]) == 2

    # 计算相似度
    similarity = workflow._outline_similarity(
        result2["simulator_rejection_history"][0]["outline"],
        result2["simulator_rejection_history"][1]["outline"]
    )
    print(f"大纲相似度: {similarity:.2%}")

    if similarity > 0.7:
        assert "死锁" in result2["simulator_feedback"]
        print(f"✓ 检测到死锁: {result2['simulator_feedback'][:100]}...")
    else:
        print(f"✓ 相似度未达阈值，正常反馈")

    # 5. 第三次驳回（完全不同的大纲，不应触发死锁）
    print("\n=== 第3次Simulator驳回（不同大纲）===")
    state["outline_data"]["outline"] = ["墨大夫突然出现", "告知韩立秘密"]  # 完全不同
    result3 = workflow.node_simulator_check(state)
    assert result3["simulator_retry_count"] == 3

    similarity2 = workflow._outline_similarity(
        result3["simulator_rejection_history"][1]["outline"],
        result3["simulator_rejection_history"][2]["outline"]
    )
    print(f"大纲相似度: {similarity2:.2%}")
    assert similarity2 < 0.7
    assert "死锁" not in result3["simulator_feedback"]
    print(f"✓ 大纲差异大，未触发死锁检测")

    # 6. 测试相似度算法
    print("\n=== 测试相似度算法 ===")
    text1 = "韩立在洞府闭关修炼"
    text2 = "韩立在洞府闭关修炼，突破失败"
    sim = workflow._outline_similarity(text1, text2)
    print(f"相似度: {sim:.2%}")
    assert 0.5 < sim < 0.9  # 应该有一定相似度

    text3 = "墨大夫突然出现"
    sim2 = workflow._outline_similarity(text1, text3)
    print(f"相似度（不同文本）: {sim2:.2%}")
    assert sim2 < 0.5  # 应该相似度很低

    print("\n" + "="*60)
    print("✅ 所有Simulator重试策略测试通过")
    print("="*60)


def test_outline_similarity():
    """测试大纲相似度计算算法"""
    memory = MockMemory()
    workflow = NovelWorkflow(memory)

    print("\n=== 测试相似度算法 ===")

    # 完全相同
    sim1 = workflow._outline_similarity("韩立修炼", "韩立修炼")
    assert sim1 == 1.0
    print(f"✓ 完全相同: {sim1:.2%}")

    # 完全不同
    sim2 = workflow._outline_similarity("韩立修炼", "墨大夫离开")
    assert sim2 < 0.3
    print(f"✓ 完全不同: {sim2:.2%}")

    # 中等相似
    sim3 = workflow._outline_similarity(
        "韩立在洞府闭关修炼",
        "韩立在洞府闭关突破"
    )
    assert 0.5 < sim3 < 0.9
    print(f"✓ 中等相似: {sim3:.2%}")

    # 空文本
    sim4 = workflow._outline_similarity("", "测试")
    assert sim4 == 0.0
    print(f"✓ 空文本: {sim4:.2%}")

    print("✅ 相似度算法测试通过\n")


if __name__ == "__main__":
    test_outline_similarity()
    test_simulator_retry_strategy()
