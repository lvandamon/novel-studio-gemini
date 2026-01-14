"""
🔥 P4新增: 性格漂移监测器 (Character Drift Detector)

功能:
1. 追踪角色性格词频变化
2. 检测长期性格漂移
3. 生成漂移报告
4. 提供修正建议

使用场景:
- 每100章自动检测
- Director审计时调用
- 人工质检时参考
"""

import json
import sqlite3
import re
from typing import Dict, Any, List, Optional
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from core.memory import MemoryManager


@dataclass
class PersonalitySnapshot:
    """角色性格快照"""
    chapter: int
    character_name: str
    trait_frequencies: Dict[str, int] = field(default_factory=dict)
    dialogue_style_markers: Dict[str, int] = field(default_factory=dict)
    emotional_keywords: Dict[str, int] = field(default_factory=dict)
    action_patterns: Dict[str, int] = field(default_factory=dict)


class DriftDetector:
    """
    性格漂移监测器

    策略:
    1. 每N章采集一次性格快照
    2. 对比初始设定与当前快照
    3. 计算漂移指数
    4. 超过阈值时发出预警
    """

    # 性格特征词库 (用于词频统计)
    PERSONALITY_TRAITS = {
        # 正面特质
        "brave": ["勇敢", "无畏", "果敢", "刚毅", "坚强", "胆大"],
        "kind": ["善良", "仁慈", "慈悲", "温柔", "体贴", "关怀"],
        "smart": ["聪明", "睿智", "机智", "狡黠", "精明", "博学"],
        "calm": ["冷静", "沉稳", "镇定", "淡然", "从容", "平静"],
        "loyal": ["忠诚", "忠心", "守信", "义气", "信义"],

        # 负面特质
        "cruel": ["残忍", "狠毒", "冷酷", "无情", "暴虐", "凶残"],
        "cunning": ["狡诈", "阴险", "奸诈", "诡计", "城府"],
        "arrogant": ["傲慢", "狂妄", "自负", "高傲", "目中无人"],
        "coward": ["懦弱", "胆小", "怯懦", "畏惧", "退缩"],
        "greedy": ["贪婪", "贪心", "贪得", "贪欲", "贪念"],

        # 中性特质
        "quiet": ["沉默", "寡言", "内敛", "低调"],
        "passionate": ["热情", "激情", "热血", "火热"],
        "cautious": ["谨慎", "小心", "警惕", "戒备"],
        "stubborn": ["固执", "倔强", "执拗", "坚持"],
    }

    # 对话风格标记词
    DIALOGUE_MARKERS = {
        "arrogant_tone": ["哼", "哈", "呵", "切", "本座", "本尊", "本少爷", "本小姐"],
        "polite_tone": ["请", "您", "多谢", "有劳", "叨扰", "承蒙"],
        "cold_tone": ["无聊", "无趣", "不必", "退下", "滚", "够了"],
        "warm_tone": ["放心", "别怕", "没事", "我在", "相信我"],
        "ironic_tone": ["有意思", "真是", "好一个", "也罢", "随你"],
    }

    # 情绪关键词
    EMOTION_KEYWORDS = {
        "anger": ["愤怒", "暴怒", "狂怒", "恼怒", "怒火", "怒气"],
        "sadness": ["悲伤", "悲痛", "哀伤", "忧伤", "难过", "心痛"],
        "joy": ["喜悦", "高兴", "欢喜", "兴奋", "快乐", "欣喜"],
        "fear": ["恐惧", "害怕", "惊恐", "畏惧", "惶恐"],
        "surprise": ["惊讶", "震惊", "诧异", "意外", "吃惊"],
    }

    def __init__(self, memory_manager: MemoryManager, snapshot_interval: int = 50):
        self.memory = memory_manager
        self.snapshot_interval = snapshot_interval
        self._init_db()

    def _init_db(self):
        """初始化漂移监测表"""
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()

        # 性格快照表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS personality_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_name TEXT NOT NULL,
                chapter_num INTEGER NOT NULL,
                trait_data TEXT,
                dialogue_data TEXT,
                emotion_data TEXT,
                action_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(character_name, chapter_num)
            )
        ''')

        # 漂移报告表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS drift_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_name TEXT NOT NULL,
                chapter_num INTEGER NOT NULL,
                drift_score REAL,
                drift_details TEXT,
                severity TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_snapshot_char ON personality_snapshots(character_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_drift_char ON drift_reports(character_name)')

        conn.commit()
        conn.close()

    def capture_snapshot(self, character_name: str, chapter_num: int, content: str) -> PersonalitySnapshot:
        """
        捕获角色性格快照

        Args:
            character_name: 角色名
            chapter_num: 章节号
            content: 该章节内容

        Returns:
            PersonalitySnapshot 对象
        """
        snapshot = PersonalitySnapshot(
            chapter=chapter_num,
            character_name=character_name
        )

        # 提取角色相关上下文
        char_contexts = self._extract_character_context(content, character_name)

        if not char_contexts:
            return snapshot

        full_context = " ".join(char_contexts)

        # 统计性格特征词频
        for trait_category, keywords in self.PERSONALITY_TRAITS.items():
            count = sum(full_context.count(kw) for kw in keywords)
            if count > 0:
                snapshot.trait_frequencies[trait_category] = count

        # 统计对话风格标记
        for style, markers in self.DIALOGUE_MARKERS.items():
            count = sum(full_context.count(m) for m in markers)
            if count > 0:
                snapshot.dialogue_style_markers[style] = count

        # 统计情绪关键词
        for emotion, keywords in self.EMOTION_KEYWORDS.items():
            count = sum(full_context.count(kw) for kw in keywords)
            if count > 0:
                snapshot.emotional_keywords[emotion] = count

        # 持久化快照
        self._save_snapshot(snapshot)

        return snapshot

    def _extract_character_context(self, text: str, char_name: str, window: int = 200) -> List[str]:
        """提取角色相关上下文"""
        contexts = []
        for match in re.finditer(re.escape(char_name), text):
            start = max(0, match.start() - window)
            end = min(len(text), match.end() + window)
            contexts.append(text[start:end])
        return contexts

    def _save_snapshot(self, snapshot: PersonalitySnapshot):
        """保存快照到数据库"""
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO personality_snapshots
            (character_name, chapter_num, trait_data, dialogue_data, emotion_data, action_data)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            snapshot.character_name,
            snapshot.chapter,
            json.dumps(snapshot.trait_frequencies, ensure_ascii=False),
            json.dumps(snapshot.dialogue_style_markers, ensure_ascii=False),
            json.dumps(snapshot.emotional_keywords, ensure_ascii=False),
            json.dumps(snapshot.action_patterns, ensure_ascii=False)
        ))

        conn.commit()
        conn.close()

    def get_snapshots(self, character_name: str, limit: int = 10) -> List[PersonalitySnapshot]:
        """获取角色的历史快照"""
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT chapter_num, trait_data, dialogue_data, emotion_data, action_data
            FROM personality_snapshots
            WHERE character_name = ?
            ORDER BY chapter_num DESC
            LIMIT ?
        ''', (character_name, limit))

        rows = cursor.fetchall()
        conn.close()

        snapshots = []
        for row in rows:
            snapshot = PersonalitySnapshot(
                chapter=row[0],
                character_name=character_name,
                trait_frequencies=json.loads(row[1]) if row[1] else {},
                dialogue_style_markers=json.loads(row[2]) if row[2] else {},
                emotional_keywords=json.loads(row[3]) if row[3] else {},
                action_patterns=json.loads(row[4]) if row[4] else {}
            )
            snapshots.append(snapshot)

        return list(reversed(snapshots))  # 按时间正序

    def calculate_drift(self, character_name: str, current_chapter: int) -> Dict[str, Any]:
        """
        计算性格漂移指数

        策略:
        1. 获取初始快照 (前10章)
        2. 获取最新快照 (最近10章)
        3. 对比词频分布变化
        4. 计算漂移分数

        Returns:
            Dict with drift_score, drift_details, severity, recommendations
        """
        snapshots = self.get_snapshots(character_name, limit=100)

        if len(snapshots) < 3:
            return {
                "drift_score": 0,
                "severity": "UNKNOWN",
                "message": "快照数据不足,无法计算漂移"
            }

        # 初始状态 (前3个快照的平均)
        initial_snapshots = snapshots[:3]
        initial_profile = self._merge_snapshots(initial_snapshots)

        # 当前状态 (最近3个快照的平均)
        recent_snapshots = snapshots[-3:]
        current_profile = self._merge_snapshots(recent_snapshots)

        # 计算各维度漂移
        trait_drift = self._calculate_distribution_drift(
            initial_profile["traits"],
            current_profile["traits"]
        )

        dialogue_drift = self._calculate_distribution_drift(
            initial_profile["dialogue"],
            current_profile["dialogue"]
        )

        emotion_drift = self._calculate_distribution_drift(
            initial_profile["emotions"],
            current_profile["emotions"]
        )

        # 综合漂移分数 (加权平均)
        total_drift = (
            trait_drift * 0.5 +
            dialogue_drift * 0.3 +
            emotion_drift * 0.2
        )

        # 严重性评估
        if total_drift > 0.6:
            severity = "CRITICAL"
        elif total_drift > 0.4:
            severity = "WARNING"
        elif total_drift > 0.2:
            severity = "NOTICE"
        else:
            severity = "NORMAL"

        # 生成详细报告
        details = self._generate_drift_details(
            initial_profile, current_profile,
            trait_drift, dialogue_drift, emotion_drift
        )

        # 保存报告
        self._save_drift_report(character_name, current_chapter, total_drift, details, severity)

        return {
            "drift_score": round(total_drift, 3),
            "severity": severity,
            "trait_drift": round(trait_drift, 3),
            "dialogue_drift": round(dialogue_drift, 3),
            "emotion_drift": round(emotion_drift, 3),
            "details": details,
            "recommendations": self._generate_recommendations(
                character_name, severity, details
            )
        }

    def _merge_snapshots(self, snapshots: List[PersonalitySnapshot]) -> Dict[str, Dict[str, float]]:
        """合并多个快照为平均分布"""
        merged = {
            "traits": defaultdict(float),
            "dialogue": defaultdict(float),
            "emotions": defaultdict(float)
        }

        if not snapshots:
            return merged

        for s in snapshots:
            for k, v in s.trait_frequencies.items():
                merged["traits"][k] += v
            for k, v in s.dialogue_style_markers.items():
                merged["dialogue"][k] += v
            for k, v in s.emotional_keywords.items():
                merged["emotions"][k] += v

        # 归一化
        n = len(snapshots)
        for category in merged:
            total = sum(merged[category].values())
            if total > 0:
                for k in merged[category]:
                    merged[category][k] = merged[category][k] / total

        return merged

    def _calculate_distribution_drift(self, dist1: Dict[str, float], dist2: Dict[str, float]) -> float:
        """
        计算两个分布之间的漂移程度

        使用 Jensen-Shannon 散度的简化版本
        """
        all_keys = set(dist1.keys()) | set(dist2.keys())

        if not all_keys:
            return 0.0

        total_diff = 0.0
        for key in all_keys:
            v1 = dist1.get(key, 0)
            v2 = dist2.get(key, 0)
            total_diff += abs(v1 - v2)

        # 归一化到 0-1 范围
        return min(1.0, total_diff / 2)

    def _generate_drift_details(self, initial: Dict, current: Dict,
                                 trait_drift: float, dialogue_drift: float,
                                 emotion_drift: float) -> Dict[str, Any]:
        """生成漂移详细信息"""
        details = {
            "trait_changes": [],
            "dialogue_changes": [],
            "emotion_changes": []
        }

        # 性格特征变化
        for trait in set(initial["traits"].keys()) | set(current["traits"].keys()):
            old_val = initial["traits"].get(trait, 0)
            new_val = current["traits"].get(trait, 0)
            if abs(old_val - new_val) > 0.1:
                change = "增强" if new_val > old_val else "减弱"
                details["trait_changes"].append(f"{trait}: {change} ({old_val:.2f} -> {new_val:.2f})")

        # 对话风格变化
        for style in set(initial["dialogue"].keys()) | set(current["dialogue"].keys()):
            old_val = initial["dialogue"].get(style, 0)
            new_val = current["dialogue"].get(style, 0)
            if abs(old_val - new_val) > 0.1:
                change = "增强" if new_val > old_val else "减弱"
                details["dialogue_changes"].append(f"{style}: {change}")

        # 情绪倾向变化
        for emotion in set(initial["emotions"].keys()) | set(current["emotions"].keys()):
            old_val = initial["emotions"].get(emotion, 0)
            new_val = current["emotions"].get(emotion, 0)
            if abs(old_val - new_val) > 0.15:
                change = "增多" if new_val > old_val else "减少"
                details["emotion_changes"].append(f"{emotion}: {change}")

        return details

    def _generate_recommendations(self, character_name: str, severity: str,
                                   details: Dict) -> List[str]:
        """生成修正建议"""
        recommendations = []

        if severity == "CRITICAL":
            recommendations.append(f"⚠️ {character_name} 性格严重漂移!建议人工审核最近10章")
            recommendations.append("建议检查该角色的黄金锚点是否被正确注入")

        if severity in ["CRITICAL", "WARNING"]:
            if details.get("trait_changes"):
                recommendations.append(f"性格特征变化: {', '.join(details['trait_changes'][:3])}")
            if details.get("dialogue_changes"):
                recommendations.append("建议在Writer提示词中强调角色原有对话风格")

        if severity == "NOTICE":
            recommendations.append("轻微漂移属于正常角色成长,但建议持续监控")

        return recommendations

    def _save_drift_report(self, character_name: str, chapter_num: int,
                           drift_score: float, details: Dict, severity: str):
        """保存漂移报告"""
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO drift_reports
            (character_name, chapter_num, drift_score, drift_details, severity)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            character_name, chapter_num, drift_score,
            json.dumps(details, ensure_ascii=False), severity
        ))

        conn.commit()
        conn.close()

    def generate_full_report(self, current_chapter: int) -> str:
        """
        生成所有主要角色的漂移报告

        通常每100章调用一次
        """
        lines = ["=" * 50, f"📊 性格漂移监测报告 (第{current_chapter}章)", "=" * 50]

        # 获取主要角色
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT name FROM characters
            WHERE json_extract(data, '$.importance') IN ('Protagonist', 'Major')
        ''')
        rows = cursor.fetchall()
        conn.close()

        major_characters = [r[0] for r in rows]

        if not major_characters:
            return "暂无主要角色数据"

        critical_count = 0
        warning_count = 0

        for char_name in major_characters:
            result = self.calculate_drift(char_name, current_chapter)

            status_icon = {
                "CRITICAL": "🔴",
                "WARNING": "🟡",
                "NOTICE": "🟠",
                "NORMAL": "🟢",
                "UNKNOWN": "⚪"
            }.get(result["severity"], "⚪")

            lines.append(f"\n{status_icon} 【{char_name}】")
            lines.append(f"   漂移指数: {result['drift_score']}")
            lines.append(f"   严重性: {result['severity']}")

            if result.get("recommendations"):
                for rec in result["recommendations"][:2]:
                    lines.append(f"   → {rec}")

            if result["severity"] == "CRITICAL":
                critical_count += 1
            elif result["severity"] == "WARNING":
                warning_count += 1

        lines.append("\n" + "=" * 50)
        lines.append(f"统计: {critical_count}个严重漂移, {warning_count}个警告")

        return "\n".join(lines)

    def should_trigger_detection(self, chapter_num: int) -> bool:
        """判断是否应该触发漂移检测"""
        return chapter_num > 0 and chapter_num % self.snapshot_interval == 0
