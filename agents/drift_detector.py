"""
🔥 P5重构: 灵魂镜像监测器 (Soul Mirror Drift Detector)

不再依赖词频统计，而是使用 LLM 进行"角色模拟对抗测试"。
Role: "The Mirror of Truth"
"""

import json
import sqlite3
import re
from typing import Dict, Any, List, Optional
from langchain_core.output_parsers import StrOutputParser
from core.memory import MemoryManager
from core.llm import get_deepseek_chat
from core.prompts import SOUL_MIRROR_PROMPT
from core.json_repair import clean_json

class DriftDetector:
    def __init__(self, memory_manager: MemoryManager, check_interval: int = 5):
        self.memory = memory_manager
        self.check_interval = check_interval
        # 使用较聪明的模型进行判决
        self.llm = get_deepseek_chat(temperature=0.3) 
        self.chain = SOUL_MIRROR_PROMPT | self.llm | StrOutputParser()
        self._init_db()

    def _init_db(self):
        """初始化漂移监测表 (Simplified)"""
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()
        
        # 漂移报告表 (保留旧表名兼容，但结构微调)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS drift_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_name TEXT NOT NULL,
                chapter_num INTEGER NOT NULL,
                drift_score REAL, -- 这里存 consistency_score (0-100)
                drift_details TEXT, -- JSON: simulation, reason
                severity TEXT, -- 'PASS' | 'FAIL'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def should_trigger_detection(self, chapter_num: int) -> bool:
        return chapter_num > 0 and chapter_num % self.check_interval == 0

    def _extract_character_scene(self, content: str, char_name: str, window: int = 300) -> str:
        """
        提取该角色的'戏份'。
        简单策略：找到名字出现的地方，截取前后文。
        如果出现多次，拼接前2次和最后1次，避免 context 过长。
        """
        matches = list(re.finditer(re.escape(char_name), content))
        if not matches: return ""
        
        # 取头、中、尾
        selected_matches = matches[:1] + matches[-1:] if len(matches) > 1 else matches
        
        snippets = []
        for m in selected_matches:
            start = max(0, m.start() - window)
            end = min(len(content), m.end() + window)
            snippets.append(f"...{content[start:end]}...")
            
        return "\n".join(snippets)

    def run_mirror_test(self, chapter_num: int, content: str, char_name: str) -> Dict[str, Any]:
        """
        执行灵魂镜像测试
        """
        # 1. 获取锚点
        anchors = self.memory.get_character_anchors(char_name)
        if not anchors: 
            return {"status": "SKIPPED", "reason": "No anchors defined"}

        # 2. 提取戏份
        actual_text = self._extract_character_scene(content, char_name)
        if not actual_text:
            return {"status": "SKIPPED", "reason": "Character not active in this chapter"}

        # 3. 获取情境 (Summary)
        summary = self.memory.get_chapter_summary(chapter_num)
        
        # 4. LLM 判决
        try:
            print(f"   🪞 Running Soul Mirror Test for {char_name} (Ch{chapter_num})...")
            response = self.chain.invoke({
                "anchors": anchors,
                "situation": summary,
                "actual_text": actual_text
            })
            
            cleaned = clean_json(response)
            result = json.loads(cleaned)
            
            # 5. 存储结果
            self._save_report(char_name, chapter_num, result)
            
            return result
            
        except Exception as e:
            print(f"   ⚠️ Soul Mirror Failed: {e}")
            return {"status": "ERROR", "error": str(e)}

    def _save_report(self, char_name: str, chapter_num: int, result: Dict):
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()
        
        details = {
            "simulation": result.get("simulation"),
            "reason": result.get("reason")
        }
        
        score = result.get("consistency_score", 100)
        severity = "FAIL" if score < 60 else "PASS"
        
        cursor.execute('''
            INSERT INTO drift_reports (character_name, chapter_num, drift_score, drift_details, severity)
            VALUES (?, ?, ?, ?, ?)
        ''', (char_name, chapter_num, score, json.dumps(details, ensure_ascii=False), severity))
        
        conn.commit()
        conn.close()

    def generate_full_report(self, current_chapter: int) -> str:
        """为 Director 生成汇总报告"""
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()
        
        # 获取本章的所有报告
        cursor.execute('''
            SELECT character_name, drift_score, drift_details, severity
            FROM drift_reports
            WHERE chapter_num = ? AND severity = 'FAIL'
        ''', (current_chapter,))
        
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return "✅ 本章灵魂镜像测试通过 (No OOC detected)."
            
        lines = ["⚠️ **警告：检测到性格漂移 (OOC Detected)**"]
        for r in rows:
            name, score, details_json, _ = r
            details = json.loads(details_json)
            lines.append(f"- **{name}** (一致性: {score}%): {details.get('reason')}")
            lines.append(f"  *Soul Simulation*: \"{details.get('simulation')[:50]}...\"")
            
        return "\n".join(lines)