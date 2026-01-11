from core.llm import get_deepseek_chat
from core.prompts import WRITER_GEN_CHAPTER_PROMPT, WRITER_REFLECT_PROMPT, WRITER_REFINE_PROMPT
from langchain_core.output_parsers import StrOutputParser

class WriterAgent:
    def __init__(self):
        self.llm = get_deepseek_chat() # V3 for writing
        
        # Define chains
        self.write_chain = WRITER_GEN_CHAPTER_PROMPT | self.llm | StrOutputParser()
        self.reflect_chain = WRITER_REFLECT_PROMPT | self.llm | StrOutputParser()
        self.refine_chain = WRITER_REFINE_PROMPT | self.llm | StrOutputParser()

    def write_chapter(self, outline: str, context_package: str = "暂无额外设定") -> str:
        """
        调用 V3 模型根据大纲撰写正文，包含自审循环。
        Draft -> Critique -> Refine
        """
        print("✍️ Writer: 正在撰写初稿...")
        draft = self.write_chain.invoke({
            "outline": outline,
            "context_package": context_package
        })
        
        print("🤔 Writer: 正在自我审视...")
        critique = self.reflect_chain.invoke({
            "outline": outline,
            "draft": draft
        })
        
        if "PASS" in critique or len(critique) < 10:
            print("✅ Writer: 初稿通过自审。 ")
            return draft
        else:
            print(f"⚠️ Writer: 发现问题，正在修稿...\n   意见: {critique[:100]}...")
            final_version = self.refine_chain.invoke({
                "draft": draft,
                "critique": critique
            })
            return final_version