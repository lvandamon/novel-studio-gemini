from core.llm import get_deepseek_reasoner
from core.prompts import EDITOR_GEN_OUTLINE_PROMPT
from langchain_core.output_parsers import StrOutputParser

import json
import re
from core.llm import get_deepseek_reasoner
from core.prompts import EDITOR_GEN_OUTLINE_PROMPT
from langchain_core.output_parsers import StrOutputParser

class EditorAgent:
    def __init__(self):
        self.llm = get_deepseek_reasoner()
        self.chain = EDITOR_GEN_OUTLINE_PROMPT | self.llm | StrOutputParser()

    def generate_outline(self, context_package: str, chapter_num: int) -> dict:
        """
        调用 R1 模型生成章节大纲，并解析 JSON 输出
        返回: {"outline": str, "active_characters": list}
        """
        print(f"🕵️‍♂️ 主编 (Editor) 正在思考第 {chapter_num} 章大纲...")
        raw_output = self.chain.invoke({
            "context": context_package,
            "chapter_num": chapter_num
        })
        
        # 尝试提取 JSON
        try:
            # 匹配 ```json ... ``` 或直接寻找 {...}
            json_match = re.search(r"```json\s*(.*?)\s*```", raw_output, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 兜底：尝试找最外层的大括号
                json_match = re.search(r"\{.*\}", raw_output, re.DOTALL)
                json_str = json_match.group(0) if json_match else "{}"
            
            data = json.loads(json_str)
            
            # 确保有必要的字段
            if "outline" not in data: data["outline"] = raw_output # 降级：如果解析失败，把全文当大纲
            if "active_characters" not in data: data["active_characters"] = []
            
            return data
            
        except Exception as e:
            print(f"⚠️ 大纲解析失败: {e}")
            return {
                "outline": raw_output, # 容错
                "active_characters": []
            }
