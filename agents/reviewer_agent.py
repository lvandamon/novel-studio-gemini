import json
import re
from typing import Dict, Any, List
from langchain_core.output_parsers import StrOutputParser
from core.llm import get_deepseek_reasoner
from core.prompts import REVIEWER_CHECK_PROMPT
from core.memory import MemoryManager

class ReviewerAgent:
    def __init__(self, memory_manager: MemoryManager):
        # Reviewer 必须用 R1 (Reasoner)，因为它要进行极其精细的逻辑找茬
        self.llm = get_deepseek_reasoner()
        self.chain = REVIEWER_CHECK_PROMPT | self.llm | StrOutputParser()
        self.memory = memory_manager

    def _clean_json(self, text: str) -> str:
        # Remove <think> blocks
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        # Strip markdown
        text = text.replace("```json", "").replace("```", "").strip()
        # Find JSON block
        match = re.search(r'(\{.*\})', text, re.DOTALL)
        if match:
            return match.group(1)
        return text

    def review_draft(self, content: str, chapter_num: int, active_characters: List[str] = None) -> str:
        """
        审核章节内容，检查逻辑冲突并记录遥测数据。
        返回: "PASS" 或 修改建议文本。
        """
        print(f"🧐 Reviewer: 正在进行逻辑审计 (DeepSeek-R1)...")
        
        # 1. 确定活跃角色
        if not active_characters:
            all_chars = [c['name'] for c in self.memory.get_all_characters_list()]
            active_characters = [name for name in all_chars if name in content]
        
        # 2. 获取上下文资料
        bible_context = self.memory.get_bible_context(query=content[:500], active_entities=active_characters)
        hard_logic_snapshot = self.memory.get_hard_logic_snapshot(active_characters)
        memory_context = self.memory.query_related_context(content[:500], k=5)

        try:
            full_context = f"""
{bible_context}

【硬逻辑快照】
{hard_logic_snapshot}

【历史记忆】
{memory_context}
"""
            response = self.chain.invoke({
                "memory_context": full_context,
                "content": content
            })
            
            # 3. 解析结果
            clean_res = self._clean_json(response)
            result_data = json.loads(clean_res)
            
            # 4. 记录遥测数据
            metrics = result_data.get("metrics", {})
            metrics["critique"] = result_data.get("critique", "")
            
            self.memory.log_chapter_metrics(chapter_num, metrics)
            
            status = result_data.get("status", "PASS")
            
            if status == "PASS":
                print(f"   ✅ Reviewer: 审核通过 (Score: {metrics.get('plot_logic_score')})")
                return "PASS"
            else:
                suggestion = result_data.get("suggestion", "请修改逻辑漏洞。")
                print(f"   🚩 Reviewer: 发现隐患! -> {suggestion}")
                return suggestion

        except json.JSONDecodeError:
            print(f"   ⚠️ Reviewer JSON 解析失败，回退到原始文本检查。")
            # Fallback simple check (if model failed to output JSON)
            if "PASS" in response and len(response) < 50:
                return "PASS"
            return response
            
        except Exception as e:
            print(f"   ⚠️ Reviewer 审计中断: {e}")
            return "PASS"