import json
import re
from typing import Dict, Any, List
from langchain_core.output_parsers import StrOutputParser
from core.llm import get_deepseek_reasoner, get_deepseek_chat
from core.prompts import REVIEWER_CHECK_PROMPT, ANCHOR_VIOLATION_CHECK_PROMPT
from core.memory import MemoryManager
from core.physics_validator import PhysicsValidator  # 🔥 P1新增
from core.style_checker import StyleChecker  # 🔥 P2新增
from core.world_consistency import WorldConsistencyEngine # 🔥 P3新增

class ReviewerAgent:
    def __init__(self, memory_manager: MemoryManager):
        # Reviewer 必须用 R1 (Reasoner)，因为它要进行极其精细的逻辑找茬
        self.llm = get_deepseek_reasoner()
        self.chain = REVIEWER_CHECK_PROMPT | self.llm | StrOutputParser()
        self.memory = memory_manager
        self.physics_validator = PhysicsValidator(memory_manager)  # 🔥 P1新增
        self.style_checker = StyleChecker() # 🔥 P2新增: 文风质检
        self.world_engine = WorldConsistencyEngine(memory_manager) # 🔥 P3新增: 世界一致性

        # 🔥 P0新增: 锚点校验专用轻量LLM (快速校验)
        self.anchor_validator_llm = get_deepseek_chat(temperature=0.1)
        self.anchor_chain = ANCHOR_VIOLATION_CHECK_PROMPT | self.anchor_validator_llm | StrOutputParser()

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

    def _validate_anchors_post_generation(self, content: str, active_characters: List[str], chapter_num: int) -> Dict[str, Any]:
        """
        🔥 P0新增: 后置锚点校验 (Post-Generation Anchor Validation)

        在Writer生成内容后，专门检查是否存在OOC违规。
        这是针对Simulator仅检查大纲的补充。

        Returns:
            Dict with keys: has_violation, violations, severity
        """
        result = {
            "has_violation": False,
            "violations": [],
            "max_severity": "NONE"
        }

        if not active_characters:
            return result

        # 收集所有角色的锚点
        all_anchors = []
        for char_name in active_characters:
            anchors_text = self.memory.get_character_anchors(char_name)
            if anchors_text:
                all_anchors.append(f"## {char_name}\n{anchors_text}")

        if not all_anchors:
            return result  # 无锚点则跳过

        anchors_combined = "\n\n".join(all_anchors)

        # 提取角色相关的内容片段 (减少token消耗)
        char_snippets = []
        for char_name in active_characters:
            # 找到所有提及该角色的段落
            paragraphs = content.split('\n\n')
            for para in paragraphs:
                if char_name in para:
                    char_snippets.append(para[:500])  # 每段最多500字

        if not char_snippets:
            return result

        content_sample = "\n---\n".join(char_snippets[:10])  # 最多10个片段

        try:
            print("   ⚓ 执行后置锚点校验...")
            response = self.anchor_chain.invoke({
                "anchors": anchors_combined,
                "content": content_sample
            })

            clean_res = self._clean_json(response)
            validation_result = json.loads(clean_res)

            violations = validation_result.get("violations", [])

            if violations:
                result["has_violation"] = True
                result["violations"] = violations

                # 计算最高严重性
                severities = [v.get("severity", "WARNING") for v in violations]
                if "CRITICAL" in severities:
                    result["max_severity"] = "CRITICAL"
                elif "ERROR" in severities:
                    result["max_severity"] = "ERROR"
                else:
                    result["max_severity"] = "WARNING"

                print(f"   ⚠️ 发现 {len(violations)} 个锚点违规! 最高等级: {result['max_severity']}")
                for v in violations[:3]:  # 显示前3个
                    print(f"      - [{v.get('severity')}] {v.get('character')}: {v.get('issue')[:50]}...")
            else:
                print("   ✅ 锚点校验通过")

            return result

        except Exception as e:
            print(f"   ⚠️ 锚点校验失败: {e}，默认放行")
            return result

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

        # 🔥 P1新增: 物理约束验证
        physics_violations = self.physics_validator.validate_draft(
            content, active_characters, chapter_num
        )
        physics_report = self.physics_validator.generate_validation_report(physics_violations)

        # 🔥 P3新增: 世界一致性验证 (经济/地理)
        world_violations = self.world_engine.generate_report(content, active_characters, chapter_num)
        world_report = ""
        if world_violations:
            world_report = "\n【🌍 世界一致性警告】\n"
            for v in world_violations:
                world_report += f"- {v['detail']}\n"
            print(f"   ⚠️ 发现 {len(world_violations)} 个世界一致性冲突!")

        # 如果有致命违规,直接拦截
        critical_violations = [v for v in physics_violations if v['severity'] == 'CRITICAL']
        # 经济逻辑崩坏也视作严重错误
        world_critical = [v for v in world_violations if v.get('severity') == 'ERROR']
        
        if critical_violations or world_critical:
            print(f"   🔴 检测到致命逻辑违规,强制拦截!")
            return json.dumps({
                "status": "BLOCK",
                "suggestion": physics_report + "\n" + world_report,
                "metrics": {
                    "physics_violation_count": len(physics_violations) + len(world_violations),
                    "plot_logic_score": 0,
                    "alignment_score": 0
                }
            })

        # 🔥 P2新增: 文风一致性检查 (Style Check)
        # 获取当前意图对应的样板 (简单起见，取通用和当前类型的)
        # 这里我们假设一个默认类型，或者应该从外部传入 intent? 
        # 为了不修改接口签名太复杂，我们先取通用的 'Narrative' 和 'Description'
        style_samples = self.memory.get_style_sample_list(tags=["Narrative", "Action", "Scenery"], limit=5)
        style_result = self.style_checker.check_style_consistency(content, style_samples)
        
        style_report = ""
        style_score = style_result['score']
        if not style_result['passed']:
            print(f"   ⚠️ 文风一致性警告 (Score: {style_score:.1f})")
            print(f"   {style_result['drift_details']}")
            style_report = f"\n【文风一致性警告】\n得分仅 {style_score:.1f}/100。检测到文风漂移：\n{style_result['drift_details']}\n请调整笔触，保持与前文一致的语感。"

            # 如果分数极低，可以考虑阻断
            if style_score < 50:
                 return json.dumps({
                    "status": "BLOCK",
                    "suggestion": f"❌ 文风严重崩坏 (Score {style_score})。{style_result['drift_details']}",
                    "metrics": {
                        "style_score": style_score,
                        "plot_logic_score": 60, # 降级
                    }
                })

        # 🔥 P0新增: 后置锚点校验 (OOC检测)
        anchor_validation = self._validate_anchors_post_generation(content, active_characters, chapter_num)
        if anchor_validation["has_violation"] and anchor_validation["max_severity"] == "CRITICAL":
            # 致命OOC违规,直接拦截
            ooc_report = "❌ 检测到致命OOC违规 (Out Of Character):\n"
            for v in anchor_validation["violations"]:
                ooc_report += f"- [{v.get('severity')}] {v.get('character')}: {v.get('issue')}\n"
                ooc_report += f"  违规内容: {v.get('evidence', 'N/A')[:100]}...\n"
                ooc_report += f"  修改建议: {v.get('suggestion', '请重写该角色的言行')}\n"

            print(f"   🔴 检测到致命OOC违规,强制拦截!")
            return json.dumps({
                "status": "BLOCK",
                "suggestion": ooc_report,
                "metrics": {
                    "character_consistency_score": 0,
                    "plot_logic_score": 50,
                    "alignment_score": 50
                }
            })

        try:
            full_context = f"""
{bible_context}

【硬逻辑快照】
{hard_logic_snapshot}

【历史记忆】
{memory_context}

【物理约束验证】
{physics_report}

{world_report}

{style_report}
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
            metrics["style_score"] = style_score # 记录文风分
            
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