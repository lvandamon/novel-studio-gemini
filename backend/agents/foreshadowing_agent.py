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

    def get_stale_unresolved_hooks(self, current_chapter: int, threshold: int = 50, limit: int = 3) -> List[Dict]:
        """
        🔥 P6新增: 获取陈旧且未解决的伏笔 (Long-range Hook Retrieval)
        供 Director 强制唤醒。
        """
        import sqlite3
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()
        
        # 只关注 Subplot(4) 以上的伏笔，Flavor(1-3) 没必要强制回收
        cutoff_chapter = current_chapter - threshold
        
        cursor.execute('''
            SELECT id, chapter_created, content, importance 
            FROM foreshadowing 
            WHERE status = 'active' 
              AND chapter_created <= ? 
              AND importance >= 4
            ORDER BY importance DESC, chapter_created ASC
            LIMIT ?
        ''', (cutoff_chapter, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        stale_hooks = []
        for r in rows:
            stale_hooks.append({
                "id": r[0],
                "chapter_created": r[1],
                "content": r[2],
                "importance": r[3],
                "gap": current_chapter - r[1]
            })
            
        return stale_hooks

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

    def _get_dynamic_threshold(self, importance: int) -> Dict[str, float]:
        """
        🔥 P3修复 + P4升级: 根据伏笔重要性动态计算阈值

        策略:
        - Core Mystery (8-10): 严格匹配，阈值更高，避免误判
        - Subplot (4-7): 标准阈值
        - Flavor (1-3): 宽松阈值，容易匹配

        🔥 P4升级:
        - 增加关键词权重比例 (防止仅靠语义相似度误判)
        - 增加实体匹配权重
        - 增加明确标记词检测

        Returns:
            Dict with thresholds and score weights
        """
        if importance >= 8:  # Core Mystery - 需要更严格
            return {
                "high_threshold": 0.85,   # 🔥 P4: 提高到0.85
                "medium_threshold": 0.75,
                "low_threshold": 0.65,
                "semantic_weight": 50,    # 🔥 P4: 降低语义权重
                "keyword_weight": 30,
                "entity_weight": 20,      # 🔥 P4新增: 实体匹配权重
                "pass_score": 70,         # 🔥 P4: 提高通过分数
                "require_entity_match": True  # 🔥 P4: 核心伏笔必须有实体匹配
            }
        elif importance >= 4:  # Subplot - 标准
            return {
                "high_threshold": 0.78,
                "medium_threshold": 0.68,
                "low_threshold": 0.58,
                "semantic_weight": 55,
                "keyword_weight": 30,
                "entity_weight": 15,
                "pass_score": 55,
                "require_entity_match": False
            }
        else:  # Flavor - 宽松
            return {
                "high_threshold": 0.70,
                "medium_threshold": 0.58,
                "low_threshold": 0.48,
                "semantic_weight": 50,
                "keyword_weight": 35,
                "entity_weight": 15,
                "pass_score": 45,
                "require_entity_match": False
            }

    def _extract_key_entities(self, text: str) -> set:
        """
        🔥 P4新增: 提取文本中的关键实体

        识别:
        - 人名 (中文2-4字)
        - 地名 (带"山/谷/城/宗/门/派"等后缀)
        - 物品名 (带"剑/刀/丹/符/令"等后缀)
        """
        entities = set()

        # 人名模式 (简化: 2-4个中文字符)
        import re
        name_pattern = r'[\u4e00-\u9fa5]{2,4}'
        potential_names = re.findall(name_pattern, text)
        for name in potential_names:
            # 过滤常见非人名词汇
            if name not in ['但是', '因为', '所以', '如果', '虽然', '就是', '这个', '那个',
                            '什么', '怎么', '为什么', '突然', '居然', '竟然', '已经', '可能']:
                entities.add(name)

        # 地名模式
        location_pattern = r'[\u4e00-\u9fa5]{2,6}(?:山|谷|城|宗|门|派|殿|阁|洞|府|国|域|界)'
        entities.update(re.findall(location_pattern, text))

        # 物品模式
        item_pattern = r'[\u4e00-\u9fa5]{2,6}(?:剑|刀|丹|符|令|珠|镜|钟|鼎|塔|戒|环)'
        entities.update(re.findall(item_pattern, text))

        return entities

    def _check_explicit_resolution_markers(self, outline: str, hook_content: str) -> bool:
        """
        🔥 P4新增: 检查是否有明确的回收标记词

        如果大纲中明确提到"揭示/揭露/真相/解开/谜底"等词汇,
        且与伏笔内容相关,则认为是明确的回收信号
        """
        resolution_markers = [
            '揭示', '揭露', '揭开', '揭穿', '真相', '谜底', '解开', '解答',
            '原来', '终于明白', '恍然大悟', '真正原因', '背后的', '秘密是',
            '答案是', '终于知道', '事实是', '发现了', '得知了'
        ]

        outline_lower = outline.lower()
        hook_lower = hook_content.lower()

        for marker in resolution_markers:
            if marker in outline_lower:
                # 检查伏笔中的关键词是否也在大纲中
                hook_keywords = set(hook_content[i:i+3] for i in range(len(hook_content)-2) if len(hook_content[i:i+3].strip()) >= 2)
                for kw in hook_keywords:
                    if kw in outline:
                        return True
        return False

    def detect_outline_resolutions(self, outline: str) -> List[int]:
        """
        🔥 P1升级 + P3修复 + P4升级: 语义嵌入匹配 + 关键词双重验证 + 动态阈值 + 实体匹配

        策略:
        1. 使用嵌入向量计算语义相似度
        2. 关键词匹配作为辅助验证
        3. 🔥 P3修复: 根据importance动态调整阈值，避免误判核心伏笔
        4. 🔥 P4新增: 实体匹配验证 (人名/地名/物品名)
        5. 🔥 P4新增: 明确回收标记词检测

        Returns:
            List[int]: 可能被回收的伏笔ID列表
        """
        # 获取包含importance的活跃伏笔
        import sqlite3
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT id, chapter_created, content, importance FROM foreshadowing WHERE status = "active"')
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return []

        potential_resolutions = []

        # 生成大纲嵌入向量
        try:
            outline_embedding = self.memory.embeddings.embed_query(outline)
        except Exception as e:
            print(f"   ⚠️ 嵌入生成失败,回退到关键词匹配: {e}")
            outline_embedding = None

        # 🔥 P4新增: 提取大纲中的实体
        outline_entities = self._extract_key_entities(outline)

        for row in rows:
            hook_id, chapter_created, hook_content, importance = row
            if importance is None:
                importance = 5

            # 🔥 P3修复: 获取动态阈值
            thresholds = self._get_dynamic_threshold(importance)
            score = 0.0
            entity_matched = False

            # 策略1: 语义相似度
            if outline_embedding:
                try:
                    hook_embedding = self.memory.embeddings.embed_query(hook_content)
                    import numpy as np
                    similarity = np.dot(outline_embedding, hook_embedding) / (
                        np.linalg.norm(outline_embedding) * np.linalg.norm(hook_embedding)
                    )

                    # 🔥 使用动态阈值
                    if similarity > thresholds["high_threshold"]:
                        score += thresholds["semantic_weight"]
                    elif similarity > thresholds["medium_threshold"]:
                        score += thresholds["semantic_weight"] * 0.67
                    elif similarity > thresholds["low_threshold"]:
                        score += thresholds["semantic_weight"] * 0.33
                except Exception:
                    pass

            # 策略2: 关键词匹配
            keywords = set()
            for i in range(len(hook_content) - 1):
                for j in range(i+2, min(i+5, len(hook_content)+1)):
                    word = hook_content[i:j]
                    if len(word) >= 2 and word.strip():
                        keywords.add(word)

            if keywords:
                matches = sum(1 for kw in keywords if kw in outline)
                match_rate = matches / len(keywords)
                score += match_rate * thresholds["keyword_weight"]

            # 🔥 P4新增: 策略3 - 实体匹配
            hook_entities = self._extract_key_entities(hook_content)
            if hook_entities and outline_entities:
                common_entities = hook_entities & outline_entities
                if common_entities:
                    entity_matched = True
                    entity_match_rate = len(common_entities) / len(hook_entities)
                    score += entity_match_rate * thresholds.get("entity_weight", 15)
                    if len(common_entities) >= 2:
                        score += 10  # 多实体匹配奖励

            # 🔥 P4新增: 策略4 - 明确回收标记词检测
            if self._check_explicit_resolution_markers(outline, hook_content):
                score += 15  # 明确标记词奖励
                print(f"   💡 检测到明确回收标记词 (伏笔ID:{hook_id})")

            # 🔥 P4修复: 核心伏笔必须有实体匹配才能被判定为回收
            require_entity = thresholds.get("require_entity_match", False)
            if require_entity and not entity_matched:
                # 核心伏笔没有实体匹配,提高通过门槛
                effective_pass_score = thresholds["pass_score"] * 1.3
            else:
                effective_pass_score = thresholds["pass_score"]

            # 🔥 使用动态通过分数
            if score >= effective_pass_score:
                potential_resolutions.append(hook_id)
                imp_label = "Core" if importance >= 8 else ("Subplot" if importance >= 4 else "Flavor")
                entity_info = f", 实体匹配:{len(hook_entities & outline_entities) if hook_entities else 0}" if entity_matched else ""
                print(f"   🎯 检测到可能回收伏笔 ID:{hook_id} [{imp_label}] (Score:{score:.1f}, Threshold:{effective_pass_score:.1f}{entity_info})")
            elif importance >= 8 and score >= thresholds["pass_score"] * 0.8:
                # 核心伏笔接近阈值但未达到,给出提示
                print(f"   ⚠️ 核心伏笔 ID:{hook_id} 接近回收阈值 (Score:{score:.1f}/{effective_pass_score:.1f}), 建议人工确认")

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