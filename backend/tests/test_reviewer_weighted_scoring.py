"""
🔥 Reviewer加权评分系统测试

测试内容:
1. 加权综合分计算
2. 关键维度失败检测
3. 动态阈值（根据修订次数）
4. 边界情况测试
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.workflow import NovelWorkflow


class MockGraph:
    """Mock GraphManager"""
    pass


class MockMemory:
    """Mock MemoryManager for testing"""
    def __init__(self):
        self.db_path = ":memory:"
        self.graph = MockGraph()

    def get_narrative_focus(self):
        return {
            "volume": 1,
            "arc": 1,
            "beat": "冲突升级",
            "goal": "突破筑基",
            "conflict": "资源不足",
            "state": "active",
            "theme": "成长"
        }


def test_weighted_score_calculation():
    """测试加权评分计算"""
    print("\n=== 测试加权评分计算 ===")

    memory = MockMemory()
    workflow = NovelWorkflow(memory)

    # 场景1：所有维度满分
    metrics1 = {
        "plot_logic_score": 100,
        "alignment_score": 100,
        "character_consistency_score": 100,
        "style_score": 100,
        "thematic_score": 100
    }
    result1 = workflow._calculate_weighted_quality_score(metrics1)
    assert result1["weighted_score"] == 100
    assert len(result1["failed_categories"]) == 0
    print(f"✓ 场景1（满分）: 综合分={result1['weighted_score']:.1f}, 失败维度={len(result1['failed_categories'])}")

    # 场景2：逻辑分很低（权重40%）
    metrics2 = {
        "plot_logic_score": 50,  # 低于阈值75
        "alignment_score": 90,
        "character_consistency_score": 90,
        "style_score": 80,
        "thematic_score": 70
    }
    result2 = workflow._calculate_weighted_quality_score(metrics2)
    # 50*0.4 + 90*0.25 + 90*0.2 + 80*0.1 + 70*0.05 = 20 + 22.5 + 18 + 8 + 3.5 = 72
    assert 71 < result2["weighted_score"] < 73
    assert len(result2["failed_categories"]) == 1  # 逻辑分失败
    assert result2["failed_categories"][0]["category"] == "plot_logic_score"
    print(f"✓ 场景2（逻辑低分）: 综合分={result2['weighted_score']:.1f}, 失败维度={len(result2['failed_categories'])}")

    # 场景3：文风分很低（权重仅10%）
    metrics3 = {
        "plot_logic_score": 90,
        "alignment_score": 90,
        "character_consistency_score": 90,
        "style_score": 40,  # 低于阈值60
        "thematic_score": 70
    }
    result3 = workflow._calculate_weighted_quality_score(metrics3)
    # 90*0.4 + 90*0.25 + 90*0.2 + 40*0.1 + 70*0.05 = 36 + 22.5 + 18 + 4 + 3.5 = 84
    assert 83 < result3["weighted_score"] < 85
    assert len(result3["failed_categories"]) == 1  # 文风失败
    print(f"✓ 场景3（文风低分）: 综合分={result3['weighted_score']:.1f}, 失败维度={len(result3['failed_categories'])}")

    # 场景4：多个维度失败
    metrics4 = {
        "plot_logic_score": 60,  # 失败（<75）
        "alignment_score": 65,   # 失败（<70）
        "character_consistency_score": 65,  # 失败（<70）
        "style_score": 55,       # 失败（<60）
        "thematic_score": 40     # 失败（<50）
    }
    result4 = workflow._calculate_weighted_quality_score(metrics4)
    assert len(result4["failed_categories"]) == 5  # 全部失败
    # 60*0.4 + 65*0.25 + 65*0.2 + 55*0.1 + 40*0.05 = 24 + 16.25 + 13 + 5.5 + 2 = 60.75
    assert 60 < result4["weighted_score"] < 62
    print(f"✓ 场景4（多维失败）: 综合分={result4['weighted_score']:.1f}, 失败维度={len(result4['failed_categories'])}")

    print("✅ 加权评分计算测试通过\n")


def test_critical_failure_detection():
    """测试关键维度失败检测"""
    print("\n=== 测试关键维度失败检测 ===")

    memory = MockMemory()
    workflow = NovelWorkflow(memory)

    # 场景1：逻辑分失败（权重40% > 20%，属于关键维度）
    metrics1 = {
        "plot_logic_score": 60,  # 失败
        "alignment_score": 90,
        "character_consistency_score": 90,
        "style_score": 80,
        "thematic_score": 70
    }
    result1 = workflow._calculate_weighted_quality_score(metrics1)
    critical1 = [f for f in result1["failed_categories"] if f["weight"] >= 0.20]
    assert len(critical1) == 1
    assert critical1[0]["category"] == "plot_logic_score"
    print(f"✓ 场景1（逻辑失败）: 关键失败={len(critical1)}")

    # 场景2：文风失败（权重10% < 20%，非关键维度）
    metrics2 = {
        "plot_logic_score": 90,
        "alignment_score": 90,
        "character_consistency_score": 90,
        "style_score": 40,  # 失败
        "thematic_score": 70
    }
    result2 = workflow._calculate_weighted_quality_score(metrics2)
    critical2 = [f for f in result2["failed_categories"] if f["weight"] >= 0.20]
    assert len(critical2) == 0  # 文风非关键维度
    print(f"✓ 场景2（文风失败）: 关键失败={len(critical2)}")

    # 场景3：多个关键维度失败
    metrics3 = {
        "plot_logic_score": 60,  # 失败（权重40%）
        "alignment_score": 60,   # 失败（权重25%）
        "character_consistency_score": 60,  # 失败（权重20%）
        "style_score": 80,
        "thematic_score": 70
    }
    result3 = workflow._calculate_weighted_quality_score(metrics3)
    critical3 = [f for f in result3["failed_categories"] if f["weight"] >= 0.20]
    assert len(critical3) == 3
    print(f"✓ 场景3（多关键失败）: 关键失败={len(critical3)}")

    print("✅ 关键维度失败检测测试通过\n")


def test_dynamic_threshold():
    """测试动态阈值"""
    print("\n=== 测试动态阈值 ===")

    memory = MockMemory()
    workflow = NovelWorkflow(memory)

    # 构建State（边界综合分72分，但所有维度都高于各自及格线，避免触发关键维度熔断）
    import json
    metrics = {
        "plot_logic_score": 76,  # 高于阈值75
        "alignment_score": 71,   # 高于阈值70
        "character_consistency_score": 71,  # 高于阈值70
        "style_score": 61,       # 高于阈值60
        "thematic_score": 51     # 高于阈值50
    }
    # 计算综合分：76*0.4 + 71*0.25 + 71*0.2 + 61*0.1 + 51*0.05 = 30.4 + 17.75 + 14.2 + 6.1 + 2.55 = 71.0

    feedback_data = {
        "status": "PASS",
        "metrics": metrics,
        "suggestion": ""
    }

    # 测试不同修订次数
    for revision_count in range(4):
        state = {
            "review_feedback": json.dumps(feedback_data, ensure_ascii=False),
            "revision_count": revision_count,
            "chapter_num": 1,
            "narrative_plan": {},
            "narrative_focus": {},
            "outline_data": {},
            "draft_content": "",
            "final_content": None,
            "simulator_feedback": "",
            "simulator_retry_count": 0,
            "simulator_rejection_history": [],
            "reader_feedback": {},
            "director_ran": False,
            "requires_director_review": False,
            "high_risk_flag": False,
            "archivist_rejected": False,
            "intervention_reason": None,
            "flashback_injection": None
        }

        result = workflow.check_review_status(state)

        # revision=0: threshold=75, 71.0<75 -> reject
        # revision=1: threshold=70, 71.0>70 -> approve
        # revision=2: threshold=65, 71.0>65 -> approve
        # revision=3+: 强制通过

        if revision_count == 0:
            assert result == "reject", f"第{revision_count+1}次审核应驳回（71.0 < 75）"
            print(f"✓ 第{revision_count+1}次审核（阈值75）: 驳回")
        else:
            assert result == "approve", f"第{revision_count+1}次审核应通过"
            print(f"✓ 第{revision_count+1}次审核（阈值降低）: 通过")

    print("✅ 动态阈值测试通过\n")


def test_edge_cases():
    """测试边界情况"""
    print("\n=== 测试边界情况 ===")

    memory = MockMemory()
    workflow = NovelWorkflow(memory)

    # 场景1：指标缺失（应默认100分）
    metrics1 = {
        "plot_logic_score": 80
        # 其他指标缺失
    }
    result1 = workflow._calculate_weighted_quality_score(metrics1)
    # 80*0.4 + 100*0.25 + 100*0.2 + 100*0.1 + 100*0.05 = 32 + 25 + 20 + 10 + 5 = 92
    assert 91 < result1["weighted_score"] < 93
    print(f"✓ 场景1（指标缺失）: 综合分={result1['weighted_score']:.1f}")

    # 场景2：空指标
    metrics2 = {}
    result2 = workflow._calculate_weighted_quality_score(metrics2)
    assert result2["weighted_score"] == 100  # 全部默认100
    print(f"✓ 场景2（空指标）: 综合分={result2['weighted_score']:.1f}")

    # 场景3：超出范围的分数（系统直接计算，不做范围限制）
    metrics3 = {
        "plot_logic_score": 150,  # 超过100
        "alignment_score": -10     # 负数
    }
    result3 = workflow._calculate_weighted_quality_score(metrics3)
    # 150*0.4 + (-10)*0.25 + 100*0.2 + 100*0.1 + 100*0.05 = 60 - 2.5 + 20 + 10 + 5 = 92.5
    # 系统不验证范围，直接计算
    assert 92 < result3["weighted_score"] < 93  # 实际是92.5
    print(f"✓ 场景3（异常分数）: 综合分={result3['weighted_score']:.1f}")

    print("✅ 边界情况测试通过\n")


if __name__ == "__main__":
    test_weighted_score_calculation()
    test_critical_failure_detection()
    test_dynamic_threshold()
    test_edge_cases()

    print("=" * 60)
    print("✅ 所有Reviewer加权评分测试通过")
    print("=" * 60)
