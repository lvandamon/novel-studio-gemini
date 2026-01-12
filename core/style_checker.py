"""
🔥 P2新增: 文风一致性检测器 (Style Consistency Checker)

功能:
1. 提取文本的文风特征(词汇分布、句式结构)
2. 与风格样板对比计算相似度
3. 检测文风漂移并给出警告

使用场景: Reviewer审核时
"""

import re
from typing import Dict, List
from collections import Counter


class StyleChecker:
    """文风一致性检测器"""

    def __init__(self):
        # 文风特征维度
        self.feature_weights = {
            "avg_sentence_length": 0.2,  # 平均句长
            "punctuation_ratio": 0.15,    # 标点密度
            "adjective_ratio": 0.15,      # 形容词比例
            "dialogue_ratio": 0.2,        # 对话比例
            "classical_terms": 0.15,      # 文言词汇
            "vocabulary_richness": 0.15   # 词汇丰富度
        }

        # 中文标点
        self.chinese_punctuation = "，。！？；：、""''《》【】（）"

        # 形容词特征词(简化)
        self.adjective_markers = [
            "的", "地", "着", "了", "过",
            "很", "非常", "极其", "十分"
        ]

        # 文言/古雅词汇标记
        self.classical_markers = [
            "乃", "故", "然", "焉", "哉", "矣", "也", "耳",
            "吾", "汝", "尔", "君", "卿",
            "此", "彼", "其", "之", "而", "以"
        ]

    def extract_features(self, text: str) -> Dict[str, float]:
        """提取文本的文风特征向量"""
        features = {}

        # 1. 平均句长
        sentences = re.split(r'[。！？]', text)
        sentences = [s for s in sentences if s.strip()]
        if sentences:
            avg_len = sum(len(s) for s in sentences) / len(sentences)
            features["avg_sentence_length"] = avg_len
        else:
            features["avg_sentence_length"] = 0

        # 2. 标点密度
        punct_count = sum(1 for c in text if c in self.chinese_punctuation)
        total_chars = len(text)
        features["punctuation_ratio"] = punct_count / total_chars if total_chars > 0 else 0

        # 3. 形容词比例(简化:检测特征词)
        adj_count = sum(text.count(marker) for marker in self.adjective_markers)
        features["adjective_ratio"] = adj_count / total_chars if total_chars > 0 else 0

        # 4. 对话比例
        dialogue_chars = len(re.findall(r'[""](.*?)["""]', text))
        features["dialogue_ratio"] = dialogue_chars / total_chars if total_chars > 0 else 0

        # 5. 文言词汇密度
        classical_count = sum(text.count(term) for term in self.classical_markers)
        features["classical_terms"] = classical_count / total_chars if total_chars > 0 else 0

        # 6. 词汇丰富度(简化:按字计算unique ratio)
        chars = list(text)
        unique_chars = set(chars)
        features["vocabulary_richness"] = len(unique_chars) / len(chars) if chars else 0

        return features

    def calculate_similarity(self, features1: Dict, features2: Dict) -> float:
        """
        计算两个特征向量的相似度

        Returns:
            0-100分数,100表示完全相同
        """
        total_score = 0.0

        for feature_name, weight in self.feature_weights.items():
            val1 = features1.get(feature_name, 0)
            val2 = features2.get(feature_name, 0)

            # 归一化差异
            if feature_name == "avg_sentence_length":
                # 句长允许±20%偏差
                diff = abs(val1 - val2) / max(val1, val2, 1)
                score = max(0, 1 - diff / 0.2) * weight
            else:
                # 比例类特征允许±0.05偏差
                diff = abs(val1 - val2)
                score = max(0, 1 - diff / 0.05) * weight

            total_score += score

        return total_score * 100

    def check_style_consistency(self, draft: str, reference_samples: List[str]) -> Dict:
        """
        检查文风一致性

        Args:
            draft: 待检测文本
            reference_samples: 参考样本列表

        Returns:
            {"score": float, "drift_details": str, "passed": bool}
        """
        # 提取当前文本特征
        draft_features = self.extract_features(draft)

        # 计算与各参考样本的相似度
        similarities = []
        for sample in reference_samples:
            sample_features = self.extract_features(sample)
            sim = self.calculate_similarity(draft_features, sample_features)
            similarities.append(sim)

        # 平均相似度
        avg_similarity = sum(similarities) / len(similarities) if similarities else 0

        # 判断是否通过(阈值70分)
        passed = avg_similarity >= 70

        # 生成漂移详情
        drift_details = self._generate_drift_report(draft_features, reference_samples)

        return {
            "score": avg_similarity,
            "drift_details": drift_details,
            "passed": passed
        }

    def _generate_drift_report(self, draft_features: Dict, references: List[str]) -> str:
        """生成漂移详情报告"""
        if not references:
            return "无参考样本"

        # 计算参考样本的平均特征
        ref_features_list = [self.extract_features(ref) for ref in references]
        avg_ref_features = {}
        for key in self.feature_weights.keys():
            values = [f[key] for f in ref_features_list]
            avg_ref_features[key] = sum(values) / len(values)

        # 比较差异
        report_lines = []
        for key in self.feature_weights.keys():
            draft_val = draft_features[key]
            ref_val = avg_ref_features[key]
            diff_pct = ((draft_val - ref_val) / ref_val * 100) if ref_val > 0 else 0

            if abs(diff_pct) > 20:  # 偏差>20%标注
                trend = "↑偏高" if diff_pct > 0 else "↓偏低"
                report_lines.append(f"  - {key}: {trend} {abs(diff_pct):.1f}%")

        if report_lines:
            return "文风偏差明显:\n" + "\n".join(report_lines)
        else:
            return "文风基本一致"
