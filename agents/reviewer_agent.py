from core.llm import get_deepseek_reasoner
from core.prompts import REVIEWER_CHECK_PROMPT
from core.memory import MemoryManager
from langchain_core.output_parsers import StrOutputParser

class ReviewerAgent:
    def __init__(self, memory_manager: MemoryManager):
        self.llm = get_deepseek_reasoner()
        self.chain = REVIEWER_CHECK_PROMPT | self.llm | StrOutputParser()
        self.memory = memory_manager

    def review_draft(self, content: str) -> str:
        """
        检索相关记忆并审核正文
        """
        print("🧐 书评人 (Reviewer) 正在审视稿件...")
        
        # 1. 简单的关键词提取（实际项目中可能需要更复杂的提取逻辑或让 LLM 提取）
        # 这里为了演示，我们直接检索全文前 200 个字作为 context 搜索源
        query = content[:200]
        
        # 2. 从 ChromaDB 检索相关记忆
        related_memory = self.memory.query_related_context(query)
        
        # 3. 还有从 SQLite 获取角色状态（可选，这里暂略，假设 RAG 已经够用）
        
        # 4. 调用 R1 进行审核
        feedback = self.chain.invoke({
            "memory_context": related_memory,
            "content": content
        })
        
        return feedback
