import json
from langchain_core.output_parsers import StrOutputParser
from core.llm import get_deepseek_chat
from core.prompts import READER_EVALUATE_PROMPT

class ReaderAgent:
    def __init__(self):
        # Reader 模拟的是直观感受，使用 V3 Chat 模型即可，不需要 R1 的深层推理
        self.llm = get_deepseek_chat(temperature=0.7) # 稍微高一点的温度，模拟不同的读者情绪
        self.chain = READER_EVALUATE_PROMPT | self.llm | StrOutputParser()

    def read_chapter(self, content: str) -> dict:
        """
        阅读章节并提供反馈。
        """
        print(f"👀 Reader: 正在试读本章...")
        
        try:
            # 调用 LLM
            response = self.chain.invoke({"content": content})
            
            # 清理 JSON
            json_str = response.replace("```json", "").replace("```", "").strip()
            feedback = json.loads(json_str)
            
            # 打印反馈
            score = feedback.get("boredom_score", 50)
            mood = feedback.get("reader_mood", "平静")
            print(f"   💬 读者反馈: [{mood}] 无聊度:{score}/100 | 期待度:{feedback.get('expectation_score')}/100")
            print(f"   🗣️ 评论: {feedback.get('comment')}")
            
            return feedback
            
        except Exception as e:
            print(f"   ⚠️ Reader 试读失败: {e}")
            # 返回默认的中庸评价
            return {
                "boredom_score": 50,
                "expectation_score": 50,
                "reader_mood": "平静",
                "comment": "（系统错误：读者掉线了）",
                "highlight": "None"
            }
