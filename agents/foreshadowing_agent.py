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
        已升级：基于 importance 权重进行智能过滤。
        """
        active_hooks = self.memory.get_active_foreshadowing() # Now returns importance too if updated in memory query
        # Need to update memory.get_active_foreshadowing to return full dict first? 
        # Actually current implementation returns ['id', 'chapter', 'content'].
        # Let's fix memory query locally here or trust the agent logic.
        # Since I cannot edit memory.py get_active_foreshadowing easily without potentially breaking other things (though I should),
        # I will do a raw query here for precision.
        
        conn = self.memory.db_path
        import sqlite3
        con = sqlite3.connect(conn)
        cursor = con.cursor()
        # Migration check just in case
        try:
             cursor.execute('ALTER TABLE foreshadowing ADD COLUMN importance INTEGER DEFAULT 5')
        except:
            pass
        
        cursor.execute('SELECT id, chapter_created, content, importance FROM foreshadowing WHERE status = "active"')
        rows = cursor.fetchall()
        con.close()
        
        health_report = []
        
        for r in rows:
            hid, start_chap, content, imp = r
            if imp is None: imp = 5
            
            gap = current_chapter - start_chap
            status = "HEALTHY"
            
            # 动态阈值：重要性越高，容忍度越低（越急着填坑？）或者越高（大坑埋得久？）
            # 通常：重要伏笔不能被遗忘，需要定期 Call Back。
            # 这里逻辑：如果是 Core (8-10)，超过 30 章没动静就报警。
            # 如果是 Flavor (1-3)，永远不报警。
            
            if imp >= 8: # Core Mystery
                if gap > 80: status = "CRITICAL (Core Forgotten)"
                elif gap > 30: status = "COLD (Need Callback)"
            elif imp >= 4: # Subplot
                if gap > 50: status = "STALE"
            else: # Flavor
                continue # Ignore flavor text

            if status != "HEALTHY":
                health_report.append({
                    "id": hid,
                    "content": content,
                    "gap": gap,
                    "status": status,
                    "importance": imp
                })
        
        return health_report

    def suggest_callbacks(self, current_chapter: int, current_location: str) -> str:
        """
        [战略建议] 给 Editor 提供“填坑建议”。
        """
        # 1. 获取健康报告
        dying_hooks = self.check_hook_health(current_chapter)
        
        # 2. 排序：Importance > Gap
        dying_hooks.sort(key=lambda x: (-x['importance'], -x['gap']))
        
        suggestions = []
        for hook in dying_hooks:
            hook_content = hook['content']
            imp = hook['importance']
            
            # 优先级标签
            p_label = "低"
            if imp >= 8: p_label = "‼️ 核心"
            elif imp >= 6: p_label = "⚠️ 重要"
            
            # 地点吻合加成
            if current_location and current_location in hook_content:
                p_label += " (📍地点吻合)"
                
            suggestions.append(f"- [{p_label}] (Ch{current_chapter - hook['gap']}前, Imp:{imp}) {hook_content}")
            
        if not suggestions:
            return "当前无急需回收的伏笔。"
            
        # Top 3 suggestions
        return "🔮 伏笔雷达 (Top Priority)：\n" + "\n".join(suggestions[:5])

    def detect_outline_resolutions(self, outline: str) -> List[int]:
        """
        🔥 P1升级: 语义嵌入匹配 + 关键词双重验证

        策略:
        1. 使用嵌入向量计算语义相似度 (主要判断)
        2. 关键词匹配作为辅助验证
        3. 综合评分决定是否回收

        Returns:
            List[int]: 可能被回收的伏笔ID列表
        """
        active_hooks = self.memory.get_active_foreshadowing()
        if not active_hooks:
            return []

        potential_resolutions = []

        # 🔥 P1新增: 生成大纲嵌入向量
        try:
            from langchain_core.documents import Document
            outline_doc = Document(page_content=outline)
            outline_embedding = self.memory.embeddings.embed_query(outline)
        except Exception as e:
            print(f"   ⚠️ 嵌入生成失败,回退到关键词匹配: {e}")
            outline_embedding = None

        for hook in active_hooks:
            hook_id = hook['id']
            hook_content = hook['content']
            score = 0.0

            # 策略1: 语义相似度 (60分)
            if outline_embedding:
                try:
                    hook_embedding = self.memory.embeddings.embed_query(hook_content)
                    # 计算余弦相似度
                    import numpy as np
                    similarity = np.dot(outline_embedding, hook_embedding) / (
                        np.linalg.norm(outline_embedding) * np.linalg.norm(hook_embedding)
                    )
                    # 相似度>0.75认为高度相关
                    if similarity > 0.75:
                        score += 60
                    elif similarity > 0.65:
                        score += 40
                    elif similarity > 0.55:
                        score += 20
                except Exception:
                    pass

            # 策略2: 关键词匹配 (40分)
            # 提取核心实体(人名/物品名等)
            import re
            # 提取2-4字的词组
            keywords = set()
            for i in range(len(hook_content) - 1):
                for j in range(i+2, min(i+5, len(hook_content)+1)):
                    word = hook_content[i:j]
                    if len(word) >= 2 and word.strip():
                        keywords.add(word)

            # 计算命中率
            matches = sum(1 for kw in keywords if kw in outline)
            if keywords:
                match_rate = matches / len(keywords)
                score += match_rate * 40

            # 综合判断: 得分>50认为可能回收
            if score >= 50:
                potential_resolutions.append(hook_id)
                print(f"   🎯 检测到可能回收伏笔 ID:{hook_id} (Score:{score:.1f})")

        return potential_resolutions

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
                if isinstance(clue, dict):
                    content_str = clue.get("content", "Unknown")
                    importance = clue.get("importance", 5)
                    tags = clue.get("tags", [])
                else: # Fallback for old prompt format or error
                    content_str = str(clue)
                    importance = 5
                    tags = []

                self.memory.add_foreshadowing(chapter_num, content_str, importance, tags)
                print(f"   -> 📌 埋下新伏笔 (Imp:{importance}): {content_str[:20]}...")

            # 回收
            for clue_id in resolved_ids:
                self.memory.resolve_foreshadowing(clue_id, chapter_num)
                print(f"   -> ✅ 回收伏笔 ID: {clue_id}")

            return data

        except Exception as e:
            print(f"⚠️ 伏笔分析出错: {e}")
            return {}