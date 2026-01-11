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

    def _clean_think(self, text: str) -> str:
        return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    def review_draft(self, content: str, active_characters: List[str] = None) -> str:
        """
        审核章节内容，检查逻辑冲突。
        返回: "PASS" 或 修改建议文本。
        """
        print(f"🧐 Reviewer: 正在进行逻辑审计 (DeepSeek-R1)...")
        
        # 1. 确定活跃角色
        if not active_characters:
            all_chars = [c['name'] for c in self.memory.get_all_characters_list()]
            active_characters = [name for name in all_chars if name in content]
        
        # 2. 获取上下文资料
        # A. 世界圣经 (最高优先级)
        bible_context = self.memory.get_bible_context(query=content[:500], active_entities=active_characters)
        
        # B. 硬逻辑快照 (状态、位置、物品)
        hard_logic_snapshot = self.memory.get_hard_logic_snapshot(active_characters)
        
        # C. 相关历史记忆 (RAG)
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
            
            # 清理思考过程
            result = self._clean_think(response)
            
            if "PASS" in result.upper() and len(result) < 20:
                print("   ✅ Reviewer: 逻辑自洽，审核通过。 ")
                return "PASS"
            else:
                print(f"   🚩 Reviewer: 发现逻辑隐患！")
                return result

        except Exception as e:
            print(f"   ⚠️ Reviewer 审计中断: {e}")
            return "PASS"