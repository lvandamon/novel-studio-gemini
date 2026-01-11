import json
import re
from typing import List, Dict
from core.llm import get_deepseek_chat
from core.prompts import FORESHADOWING_ANALYSIS_PROMPT
from core.memory import MemoryManager
from langchain_core.output_parsers import StrOutputParser

class ForeshadowingAgent:
    def __init__(self, memory_manager: MemoryManager):
        self.llm = get_deepseek_chat(temperature=0.2)
        self.chain = FORESHADOWING_ANALYSIS_PROMPT | self.llm | StrOutputParser()
        self.memory = memory_manager

    def check_hook_health(self, current_chapter: int) -> List[Dict]:
        """
        [主动技能] 检查伏笔健康度。
        如果一个伏笔超过 20 章未被提及，标记为 "COLD" (变凉)。
        如果超过 50 章，标记为 "CRITICAL" (濒死/被遗忘)。
        """
        active_hooks = self.memory.get_active_foreshadowing()
        health_report = []
        
        for hook in active_hooks:
            start_chap = hook.get('chapter', 0)
            gap = current_chapter - start_chap
            
            status = "HEALTHY"
            if gap > 50:
                status = "CRITICAL"
            elif gap > 20:
                status = "COLD"
                
            if status != "HEALTHY":
                health_report.append({
                    "id": hook['id'],
                    "content": hook['content'],
                    "gap": gap,
                    "status": status
                })
        
        return health_report

    def suggest_callbacks(self, current_chapter: int, current_location: str) -> str:
        """
        [战略建议] 给 Editor 提供“填坑建议”。
        基于当前地点和伏笔健康度，推荐现在可以回收或推进的线索。
        """
        # 1. 获取濒死伏笔
        dying_hooks = self.check_hook_health(current_chapter)
        
        # 2. 简单的相关性过滤 (这里未来可以用向量检索做更高级的匹配)
        # 比如：如果伏笔提到“青云门”，而当前地点是“青云门”，则强烈推荐
        suggestions = []
        
        for hook in dying_hooks:
            hook_content = hook['content']
            # 简单的关键词匹配 (Baseline)
            priority = "低"
            if hook['status'] == "CRITICAL":
                priority = "高 (急需填坑)"
            
            # 如果地点匹配，优先级提升
            if current_location and current_location in hook_content:
                priority = "极高 (地点吻合)"
                
            suggestions.append(f"- [优先级:{priority}] 伏笔(Ch{current_chapter - hook['gap']}): {hook_content}")
            
        if not suggestions:
            return "当前无急需回收的濒死伏笔。"
            
        return "🔮 伏笔猎人建议回收：\n" + "\n".join(suggestions)

    def analyze_hooks(self, content: str, chapter_num: int) -> dict:
        """分析并更新伏笔 (每章结束运行)"""
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
            # 简单修复
            json_str = json_str.replace(",\n}", "\n}") 
            
            data = json.loads(json_str)
            
            # 4. 执行数据库更新
            new_clues = data.get("new_clues", [])
            resolved_ids = data.get("resolved_clue_ids", [])
            
            # 新增
            for clue in new_clues:
                self.memory.add_foreshadowing(chapter_num, clue)
                print(f"   -> 📌 埋下新伏笔: {clue[:20]}...")
            
            # 回收
            for clue_id in resolved_ids:
                self.memory.resolve_foreshadowing(clue_id, chapter_num)
                print(f"   -> ✅ 回收伏笔 ID: {clue_id}")
                
            return data
            
        except Exception as e:
            print(f"⚠️ 伏笔分析出错: {e}")
            return {}
