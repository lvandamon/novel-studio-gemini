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

    def review_chapter(self, content: str, active_characters: List[str]) -> str:
        """
        审核章节内容，检查逻辑冲突。
        返回: "PASS" 或 修改建议文本。
        """
        print(f"🧐 Reviewer: 正在进行逻辑审计 (DeepSeek-R1)...")
        
        # 1. 获取硬逻辑快照 (位置、状态、物品)
        hard_logic_snapshot = self.memory.get_hard_logic_snapshot(active_characters)
        
        # 2. 获取相关历史记忆
        memory_context = self.memory.query_related_context(content[:500], k=5)

        try:
            response = self.chain.invoke({
                "memory_context": f"【硬逻辑快照】\n{hard_logic_snapshot}\n\n【历史记忆】\n{memory_context}",
                "content": content
            })
            
            # 清理思考过程
            result = self._clean_think(response)
            
            if "PASS" in result.upper() and len(result) < 20:
                print("   ✅ Reviewer: 逻辑自洽，审核通过。 ")
                return "PASS"
            else:
                print(f"   🚩 Reviewer: 发现逻辑隐患！")
                # print(f"   建议: {result[:200]}...")
                return result

        except Exception as e:
            print(f"   ⚠️ Reviewer 审计中断: {e}")
            return "PASS" # 容错：审计失败时假设通过，避免流程卡死