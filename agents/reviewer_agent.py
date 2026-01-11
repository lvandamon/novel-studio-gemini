from typing import List
from langchain_core.documents import Document
from core.llm import get_deepseek_reasoner
from core.prompts import REVIEWER_CHECK_PROMPT
from core.memory import MemoryManager
from langchain_core.output_parsers import StrOutputParser

class ReviewerAgent:
    def __init__(self, memory_manager: MemoryManager):
        self.llm = get_deepseek_reasoner()
        self.chain = REVIEWER_CHECK_PROMPT | self.llm | StrOutputParser()
        self.memory = memory_manager

    def _get_comprehensive_context(self, content: str) -> str:
        """
        多点采样检索：将长文切片，分别检索相关记忆，去重后合并。
        解决“只看开头”导致的漏检问题。
        """
        # 1. 简单的切片策略：每 800 字取一段，取前 150 字作为 Query
        chunk_size = 800
        query_len = 150
        
        unique_docs = {} # id -> doc (使用 content hash 作为 id)
        
        # 如果内容太短，直接查一次
        if len(content) < chunk_size:
            queries = [content]
        else:
            queries = []
            for i in range(0, len(content), chunk_size):
                queries.append(content[i : i + query_len])
        
        print(f"   -> 正在执行多点检索 (采样点: {len(queries)})...")
        
        # 2. 执行检索与去重
        for q in queries:
            docs = self.memory.similarity_search(q, k=2) # 每个点查 2 条
            for doc in docs:
                # 简单去重：使用内容的前50个字符作为指纹（实际可用 hash）
                doc_id = hash(doc.page_content)
                if doc_id not in unique_docs:
                    unique_docs[doc_id] = doc
        
        # 3. 格式化结果
        if not unique_docs:
            return "暂无相关记忆。"
            
        result = []
        # 按检索到的顺序（这里字典序无所谓，LLM 能处理）
        for i, doc in enumerate(unique_docs.values()):
            source = f"[第 {doc.metadata.get('chapter', '?')} 章]"
            result.append(f"--- 历史记忆 {i+1} {source} ---\n{doc.page_content[:500]}...\n") # 限制单条记忆长度防止撑爆
            
        return "\n".join(result)

    def review_draft(self, content: str) -> str:
        """
        检索相关记忆并审核正文
        """
        print("🧐 书评人 (Reviewer) 正在审视稿件...")
        
        # 1. 获取综合上下文 (Multi-Hop Retrieval)
        related_memory = self._get_comprehensive_context(content)
        
        # 2. 调用 R1 进行审核
        # R1 的 Context Window 很大，可以一次性吞下全文 + 检索到的碎片
        feedback = self.chain.invoke({
            "memory_context": related_memory,
            "content": content
        })
        
        return feedback
