import json
import re
from core.llm import get_deepseek_chat
from core.prompts import FORESHADOWING_ANALYSIS_PROMPT
from core.memory import MemoryManager
from langchain_core.output_parsers import StrOutputParser

class ForeshadowingAgent:
    def __init__(self, memory_manager: MemoryManager):
        # 使用较低温度，保证提取的准确性
        self.llm = get_deepseek_chat(temperature=0.2)
        self.chain = FORESHADOWING_ANALYSIS_PROMPT | self.llm | StrOutputParser()
        self.memory = memory_manager

    def analyze_hooks(self, content: str, chapter_num: int) -> dict:
        """分析并更新伏笔"""
        print(f"🔮 伏笔猎人 (Foreshadowing) 正在分析线索...")
        
        # 1. 获取当前活跃伏笔
        active_hooks = self.memory.get_active_foreshadowing()
        hooks_str = json.dumps(active_hooks, ensure_ascii=False) if active_hooks else "暂无活跃伏笔"
        
        # 2. 调用 LLM
        raw_output = self.chain.invoke({
            "content": content,
            "active_hooks": hooks_str
        })
        
        # 3. 解析 JSON
        try:
            # 清理可能的 markdown
            json_str = raw_output.replace("```json", "").replace("```", "").strip()
            data = json.loads(json_str)
            
            # 4. 执行数据库更新
            new_clues = data.get("new_clues", [])
            resolved_ids = data.get("resolved_clue_ids", [])
            
            # 新增
            for clue in new_clues:
                self.memory.add_foreshadowing(chapter_num, clue)
                print(f"   -> 埋下新伏笔: {clue[:20]}...")
            
            # 回收
            for clue_id in resolved_ids:
                self.memory.resolve_foreshadowing(clue_id, chapter_num)
                print(f"   -> 回收伏笔 ID: {clue_id}")
                
            return data
            
        except Exception as e:
            print(f"⚠️ 伏笔分析出错: {e}")
            return {}
