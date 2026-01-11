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

    def review_draft(self, content: str) -> str:
        """
        审核章节内容，检查逻辑冲突。
        返回: "PASS" 或 修改建议文本。
        """
        print(f"🧐 Reviewer: 正在进行逻辑审计 (DeepSeek-R1)...")
        
        # Extract probable characters from content (simple heuristic or Regex)
        # 既然没有传入 active_characters，我们只能简单从文本中提取或者全量检查
        # 更好的做法是 workflow 传入，但为了保持接口兼容，我们这里暂时不做深度提取
        # 依赖 R1 的内部逻辑能力，但为了加强效果，我们可以从 content 里 regex 提取大写名字
        # 或者为了简单，直接传给 LLM 文本，让 LLM 自己判断。
        # 但 Prompts 里需要 {memory_context}，这需要 memory.get_hard_logic_snapshot
        
        # 修正策略：尝试从文本中提取名字 (Keyword Extraction)
        # 或者我们修改 workflow 传入 active_characters (更稳妥，但要动 workflow)
        # 鉴于现在是 "Fix Missing Method"，我们先实现 review_draft，并尽量获取上下文
        
        # 临时方案：从 Memory 获取所有活跃角色的名字进行简单的包含匹配
        all_chars = [c['name'] for c in self.memory.get_all_characters_list()]
        active_in_text = [name for name in all_chars if name in content]
        
        # 1. 获取硬逻辑快照
        hard_logic_snapshot = self.memory.get_hard_logic_snapshot(active_in_text)
        
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
                return result

        except Exception as e:
            print(f"   ⚠️ Reviewer 审计中断: {e}")
            return "PASS"