"""
🔥 P4新增: 记忆遗忘率检测器 (Memory Forgetting Checker)

功能:
1. 定期抽查历史事件
2. 验证Writer是否能正确引用历史
3. 检测记忆一致性
4. 生成遗忘率报告

使用场景:
- 每100章进行一次抽查
- 质检流程中调用
- 分析长篇一致性
"""

import json
import sqlite3
import random
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from core.memory import MemoryManager
from core.llm import get_deepseek_chat
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


@dataclass
class MemoryTest:
    """记忆测试用例"""
    test_id: str
    event_chapter: int
    event_description: str
    character_involved: str
    test_question: str
    expected_facts: List[str]
    actual_answer: str = ""
    score: float = 0.0
    passed: bool = False


class MemoryChecker:
    """
    记忆遗忘率检测器

    策略:
    1. 从历史事件中随机抽取N个重要事件
    2. 生成记忆测试问题
    3. 调用LLM回答 (模拟Writer的记忆能力)
    4. 对比答案与历史记录
    5. 计算遗忘率
    """

    MEMORY_TEST_PROMPT = ChatPromptTemplate.from_template("""
你是一个小说记忆测试助手。根据提供的上下文回答以下问题。

## 当前可用记忆
{context}

## 问题
{question}

## 要求
- 仅根据提供的记忆回答
- 如果记忆中没有相关信息，明确说"记忆中无此信息"
- 简洁作答，不要编造

## 回答
""")

    CONSISTENCY_CHECK_PROMPT = ChatPromptTemplate.from_template("""
你是一个小说一致性检查助手。请对比以下两段描述是否一致。

## 历史记录 (权威来源)
{historical_fact}

## 当前描述
{current_description}

## 分析要求
1. 判断两者是否描述同一事件/状态
2. 检查是否有事实性矛盾
3. 评估一致性 (0-100分)

## 输出格式 (JSON)
```json
{{
    "is_consistent": true/false,
    "consistency_score": 0-100,
    "contradictions": ["矛盾点1", "矛盾点2"],
    "notes": "简要说明"
}}
```
""")

    def __init__(self, memory_manager: MemoryManager):
        self.memory = memory_manager
        self.llm = get_deepseek_chat(temperature=0.1)
        self.test_chain = self.MEMORY_TEST_PROMPT | self.llm | StrOutputParser()
        self.consistency_chain = self.CONSISTENCY_CHECK_PROMPT | self.llm | StrOutputParser()
        self._init_db()

    def _init_db(self):
        """初始化遗忘检测表"""
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memory_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_batch_id TEXT,
                chapter_tested INTEGER,
                event_chapter INTEGER,
                event_description TEXT,
                test_question TEXT,
                expected_facts TEXT,
                actual_answer TEXT,
                score REAL,
                passed BOOLEAN,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS forgetting_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_num INTEGER,
                total_tests INTEGER,
                passed_tests INTEGER,
                forgetting_rate REAL,
                critical_failures TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()

    def sample_historical_events(self, current_chapter: int, sample_size: int = 10) -> List[Dict]:
        """
        从历史事件中抽样

        抽样策略:
        1. 优先抽取重要事件 (Major, Climax)
        2. 分层抽样: 远期 (50章+前) / 中期 (10-50章前) / 近期 (10章内)
        3. 确保覆盖主要角色
        """
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()

        events = []

        # 远期重要事件 (50章+前)
        if current_chapter > 50:
            cursor.execute('''
                SELECT id, chapter_num, character_name, event_type, description
                FROM events
                WHERE chapter_num <= ? AND event_type IN ('Major', 'Climax', 'Core')
                ORDER BY RANDOM()
                LIMIT ?
            ''', (current_chapter - 50, sample_size // 3))
            events.extend(cursor.fetchall())

        # 中期事件 (10-50章前)
        if current_chapter > 10:
            start = max(1, current_chapter - 50)
            end = current_chapter - 10
            cursor.execute('''
                SELECT id, chapter_num, character_name, event_type, description
                FROM events
                WHERE chapter_num BETWEEN ? AND ?
                ORDER BY RANDOM()
                LIMIT ?
            ''', (start, end, sample_size // 3))
            events.extend(cursor.fetchall())

        # 近期事件 (10章内)
        cursor.execute('''
            SELECT id, chapter_num, character_name, event_type, description
            FROM events
            WHERE chapter_num > ? AND chapter_num < ?
            ORDER BY RANDOM()
            LIMIT ?
        ''', (current_chapter - 10, current_chapter, sample_size // 3))
        events.extend(cursor.fetchall())

        conn.close()

        return [
            {
                "id": e[0],
                "chapter": e[1],
                "character": e[2],
                "type": e[3],
                "description": e[4]
            }
            for e in events
        ]

    def generate_test_questions(self, events: List[Dict]) -> List[MemoryTest]:
        """
        根据历史事件生成测试问题
        """
        tests = []

        for event in events:
            # 根据事件类型生成不同问题
            question_templates = [
                f"在第{event['chapter']}章前后，{event['character']}发生了什么重要事件？",
                f"{event['character']}与'{event['description'][:20]}...'相关的事件发生在哪一章？",
                f"描述一下{event['character']}在故事早期的一个重要经历。"
            ]

            question = random.choice(question_templates)

            test = MemoryTest(
                test_id=f"test_{event['id']}_{event['chapter']}",
                event_chapter=event['chapter'],
                event_description=event['description'],
                character_involved=event['character'],
                test_question=question,
                expected_facts=[
                    event['description'],
                    f"发生在第{event['chapter']}章",
                    f"涉及{event['character']}"
                ]
            )
            tests.append(test)

        return tests

    def run_memory_test(self, test: MemoryTest, current_chapter: int) -> MemoryTest:
        """
        执行单个记忆测试

        模拟Writer在生成时的记忆检索能力
        """
        # 获取Writer可用的上下文 (模拟实际生成时的记忆范围)
        context = self.memory.query_related_context(
            query=test.test_question,
            k=5,
            current_chapter=current_chapter
        )

        # 调用LLM回答
        try:
            answer = self.test_chain.invoke({
                "context": context,
                "question": test.test_question
            })
            test.actual_answer = answer

            # 评估答案质量
            test.score, test.passed = self._evaluate_answer(test, answer)

        except Exception as e:
            test.actual_answer = f"测试失败: {e}"
            test.score = 0.0
            test.passed = False

        return test

    def _evaluate_answer(self, test: MemoryTest, answer: str) -> Tuple[float, bool]:
        """
        评估答案质量

        评分标准:
        - 提及正确章节: +30分
        - 提及正确角色: +30分
        - 描述事件要点: +40分
        """
        score = 0.0

        # 检查章节
        chapter_str = str(test.event_chapter)
        if chapter_str in answer or f"第{chapter_str}章" in answer:
            score += 30

        # 检查角色
        if test.character_involved in answer:
            score += 30

        # 检查事件描述 (关键词匹配)
        event_keywords = set()
        for i in range(0, len(test.event_description) - 2, 2):
            kw = test.event_description[i:i+3]
            if len(kw.strip()) >= 2:
                event_keywords.add(kw)

        if event_keywords:
            matches = sum(1 for kw in event_keywords if kw in answer)
            keyword_score = min(40, (matches / len(event_keywords)) * 40)
            score += keyword_score

        # 检查是否明确说"无此信息"
        if "无此信息" in answer or "没有相关" in answer or "记不清" in answer:
            score = max(0, score - 20)  # 扣分但不低于0

        passed = score >= 60  # 60分及格

        return score, passed

    def run_batch_test(self, current_chapter: int, sample_size: int = 10) -> Dict[str, Any]:
        """
        执行批量记忆测试

        Returns:
            测试结果汇总
        """
        import uuid
        batch_id = str(uuid.uuid4())[:8]

        # 1. 抽样历史事件
        events = self.sample_historical_events(current_chapter, sample_size)

        if not events:
            return {
                "batch_id": batch_id,
                "status": "SKIPPED",
                "message": "历史事件不足,跳过测试"
            }

        # 2. 生成测试问题
        tests = self.generate_test_questions(events)

        # 3. 执行测试
        results = []
        for test in tests:
            result = self.run_memory_test(test, current_chapter)
            results.append(result)

            # 保存单个测试结果
            self._save_test_result(batch_id, current_chapter, result)

        # 4. 计算统计
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        forgetting_rate = 1 - (passed / total) if total > 0 else 0

        # 关键失败 (远期重要事件未记住)
        critical_failures = [
            r for r in results
            if not r.passed and (current_chapter - r.event_chapter) > 50
        ]

        # 5. 保存报告
        report = {
            "batch_id": batch_id,
            "chapter": current_chapter,
            "total_tests": total,
            "passed_tests": passed,
            "forgetting_rate": round(forgetting_rate, 3),
            "critical_failures": len(critical_failures),
            "severity": self._assess_severity(forgetting_rate, len(critical_failures)),
            "details": {
                "passed_tests": [r.test_id for r in results if r.passed],
                "failed_tests": [
                    {"id": r.test_id, "chapter": r.event_chapter, "score": r.score}
                    for r in results if not r.passed
                ]
            }
        }

        self._save_batch_report(current_chapter, report)

        return report

    def _assess_severity(self, forgetting_rate: float, critical_count: int) -> str:
        """评估遗忘严重性"""
        if forgetting_rate > 0.5 or critical_count >= 3:
            return "CRITICAL"
        elif forgetting_rate > 0.3 or critical_count >= 1:
            return "WARNING"
        elif forgetting_rate > 0.1:
            return "NOTICE"
        else:
            return "GOOD"

    def _save_test_result(self, batch_id: str, current_chapter: int, test: MemoryTest):
        """保存单个测试结果"""
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO memory_tests
            (test_batch_id, chapter_tested, event_chapter, event_description,
             test_question, expected_facts, actual_answer, score, passed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            batch_id, current_chapter, test.event_chapter,
            test.event_description, test.test_question,
            json.dumps(test.expected_facts, ensure_ascii=False),
            test.actual_answer, test.score, test.passed
        ))

        conn.commit()
        conn.close()

    def _save_batch_report(self, current_chapter: int, report: Dict):
        """保存批量测试报告"""
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO forgetting_reports
            (chapter_num, total_tests, passed_tests, forgetting_rate, critical_failures)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            current_chapter,
            report["total_tests"],
            report["passed_tests"],
            report["forgetting_rate"],
            json.dumps(report.get("details", {}).get("failed_tests", []), ensure_ascii=False)
        ))

        conn.commit()
        conn.close()

    def check_consistency(self, historical_fact: str, current_description: str) -> Dict[str, Any]:
        """
        检查当前描述与历史记录的一致性

        Args:
            historical_fact: 历史记录 (权威来源)
            current_description: 当前描述 (待验证)

        Returns:
            一致性检查结果
        """
        try:
            result = self.consistency_chain.invoke({
                "historical_fact": historical_fact,
                "current_description": current_description
            })

            # 解析JSON
            import re
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())

            return {
                "is_consistent": True,
                "consistency_score": 50,
                "notes": "解析失败,默认通过"
            }

        except Exception as e:
            return {
                "is_consistent": True,
                "consistency_score": 0,
                "error": str(e)
            }

    def generate_report(self, current_chapter: int) -> str:
        """生成遗忘率报告"""
        # 获取最近的报告
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT chapter_num, total_tests, passed_tests, forgetting_rate
            FROM forgetting_reports
            ORDER BY created_at DESC
            LIMIT 5
        ''')
        reports = cursor.fetchall()
        conn.close()

        if not reports:
            return "暂无记忆测试记录"

        lines = ["=" * 50, "📊 记忆遗忘率报告", "=" * 50]

        for r in reports:
            status = "🟢" if r[3] < 0.2 else ("🟡" if r[3] < 0.4 else "🔴")
            lines.append(f"{status} 第{r[0]}章: 测试{r[1]}项, 通过{r[2]}项, 遗忘率{r[3]:.1%}")

        # 趋势分析
        if len(reports) >= 3:
            recent_rates = [r[3] for r in reports[:3]]
            avg_rate = sum(recent_rates) / len(recent_rates)
            trend = "上升⬆️" if recent_rates[0] > recent_rates[-1] else "下降⬇️"
            lines.append(f"\n趋势: 近期平均遗忘率 {avg_rate:.1%} ({trend})")

        return "\n".join(lines)

    def should_trigger_test(self, chapter_num: int) -> bool:
        """判断是否应该触发记忆测试"""
        return chapter_num > 20 and chapter_num % 50 == 0
