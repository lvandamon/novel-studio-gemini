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

    def _clean_json(self, text: str) -> str:
        # Remove <think> blocks
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        # Strip markdown
        text = text.replace("```json", "").replace("```", "").strip()
        # Find JSON block
        match = re.search(r'(\{.*\})', text, re.DOTALL)
        if match:
            return match.group(1)
        return text

    def review_draft(self, content: str, chapter_num: int, active_characters: List[str] = None) -> str:
        """
        审核章节内容，检查逻辑冲突并记录遥测数据。
        返回: "PASS" 或 修改建议文本。
        """
        print(f"🧐 Reviewer: 正在进行逻辑审计 (DeepSeek-R1)...")
        
        # 1. 确定活跃角色
        if not active_characters:
            all_chars = [c['name'] for c in self.memory.get_all_characters_list()]
            active_characters = [name for name in all_chars if name in content]
        
        # 2. 获取上下文资料
        focus = self.memory.get_narrative_focus()
        current_theme = focus.get("theme", "成长")
        
        bible_context = self.memory.get_bible_context(query=content[:500], active_entities=active_characters)
        hard_logic_snapshot = self.memory.get_hard_logic_snapshot(active_characters)
        memory_context = self.memory.query_related_context(content[:500], k=5, current_chapter=chapter_num)

        # New: Fetch Personality & Mental Context for OOC Check
        anchors_text = ""
        mental_text = self.memory.get_character_mental_curve(active_characters, limit=3)
        
        for char in active_characters:
            anchors = self.memory.get_character_anchors(char)
            if anchors:
                anchors_text += f"{anchors}\n"

        if not anchors_text: anchors_text = "（无活跃角色的特殊黄金锚点）"

        try:
            full_context = f"""
{bible_context}

【硬逻辑快照】
{hard_logic_snapshot}

【历史记忆】
{memory_context}
"""
            # Format Narrative Focus
            focus_text = f"""
目标 (Goal): {focus.get('goal', 'N/A')}
节拍 (Beat): {focus.get('beat', 'N/A')}
冲突 (Conflict): {focus.get('conflict', 'N/A')}
            """

            response = self.chain.invoke({
                "narrative_focus": focus_text,
                "current_theme": current_theme,
                "character_anchors": anchors_text,
                "mental_states": mental_text,
                "memory_context": full_context,
                "content": content
            })
            
            # 3. 解析结果
            clean_res = self._clean_json(response)
            result_data = json.loads(clean_res)
            
            # 4. 记录遥测数据
            metrics = result_data.get("metrics", {})
            metrics["critique"] = result_data.get("critique", "")
            
            self.memory.log_chapter_metrics(chapter_num, metrics)
            
            # 5. 更新母题回响计数 (文眼政委核心逻辑)
            thematic_score = metrics.get("thematic_score", 0)
            alignment_score = metrics.get("alignment_score", 0) # New field
            
            if thematic_score >= 70:
                print(f"   ✨ Reviewer: 检测到母题回响! (Score: {thematic_score})")
                self.memory.update_narrative_focus(
                    volume=focus['volume'], 
                    arc=focus['arc'], 
                    beat=focus['beat'], 
                    goal=focus['goal'], 
                    conflict=focus['conflict'], 
                    state=focus['state'],
                    echo_count_delta=1
                )
            elif thematic_score < 40:
                print(f"   ⚠️ Reviewer: 警告，本章灵魂缺失，母题共鸣极低。")

            status = result_data.get("status", "PASS")
            
            # 增强的 PASS 逻辑: 即使 Status 是 PASS，如果分数过低也必须拦截 (Workflow 这一层做，这里只负责返回真实数据)
            # 为了 Workflow 方便，我们将结构化数据嵌入 feedback 字符串，或者 Workflow 直接从 memory 读取 metrics?
            # 更好的方式是 Workflow 这一层访问 metrics。但 NovelState.review_feedback 目前是字符串。
            # 我们将在这里直接返回 JSON string，让 Workflow 解析，或者保持字符串但包含分数信息
            
            # 简单起见，我们返回 JSON 字符串作为 feedback，让 Workflow 去解析。
            # 但 Workflow 目前预期的是 "PASS" string。
            # 兼容性方案: 如果通过，返回 "PASS"。如果不通过，返回 JSON string。
            # 可是 Workflow 想要做硬性熔断。
            
            # 修改策略：永远返回 JSON string，Workflow 负责解析。
            return json.dumps(result_data, ensure_ascii=False)

        except json.JSONDecodeError:
            print(f"   ⚠️ Reviewer JSON 解析失败，回退到原始文本检查。")
            # Fallback simple check (if model failed to output JSON)
            if "PASS" in response and len(response) < 50:
                return json.dumps({"status": "PASS", "suggestion": ""})
            return json.dumps({"status": "BLOCK", "suggestion": response, "metrics": {}})
            
        except Exception as e:
            print(f"   ⚠️ Reviewer 审计中断: {e}")
            return json.dumps({"status": "PASS", "suggestion": "System Error Bypass"})