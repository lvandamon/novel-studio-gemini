from typing import List
from core.llm import get_deepseek_chat
from core.prompts import WRITER_GEN_CHAPTER_PROMPT, WRITER_REFLECT_PROMPT, WRITER_REFINE_PROMPT, ANCHOR_VIOLATION_CHECK_PROMPT
from core.memory import MemoryManager
from langchain_core.output_parsers import StrOutputParser
import json

class WriterAgent:
    def __init__(self, memory_manager: MemoryManager):
        self.llm = get_deepseek_chat() # V3 for writing
        self.memory = memory_manager
        
        # Define chains
        self.write_chain = WRITER_GEN_CHAPTER_PROMPT | self.llm | StrOutputParser()
        self.reflect_chain = WRITER_REFLECT_PROMPT | self.llm | StrOutputParser()
        self.refine_chain = WRITER_REFINE_PROMPT | self.llm | StrOutputParser()
        self.anchor_check_chain = ANCHOR_VIOLATION_CHECK_PROMPT | self.llm | StrOutputParser()

    def _check_anchors(self, draft: str, active_characters: List[str]) -> str:
        """
        🔥 P1新增: 硬约束检查 (Hard Constraint Check)
        检查草稿是否违背了角色的黄金锚点。
        """
        if not active_characters:
            return ""

        print("   ⚓️ Writer: 正在进行黄金锚点硬约束检查...")
        
        # 1. 收集所有相关角色的锚点
        all_anchors = ""
        for char_name in active_characters:
            anchors = self.memory.get_character_anchors(char_name)
            if anchors:
                all_anchors += f"{anchors}\n"
        
        if not all_anchors:
            return ""

        # 2. 调用 LLM 进行专项检查
        try:
            result = self.anchor_check_chain.invoke({
                "anchors": all_anchors,
                "content": draft
            })
            
            # 清理可能的 Markdown
            result = result.replace("```json", "").replace("```", "").strip()
            if not result: return ""
            
            data = json.loads(result)
            violations = data.get("violations", [])
            
            if not violations:
                return ""
            
            # 格式化违规报告
            report = "\n🚨【致命错误：黄金锚点违规】(必须立即修正):\n"
            for v in violations:
                severity_icon = "❌" if v['severity'] == 'CRITICAL' else "⚠️"
                report += f"- {severity_icon} [{v['character']}] 违背 [{v['anchor_type']}]: {v['issue']}\n  证据: \"{v['evidence']}\"\n  建议: {v['suggestion']}\n"
            
            print(f"   ⚠️ Writer: 发现 {len(violations)} 处锚点违规！")
            return report

        except Exception as e:
            print(f"   ⚠️ 锚点检查失败: {e}")
            return ""

    def write_chapter(self, outline: str, context_package: str = "暂无额外设定", active_characters: List[str] = None) -> str:
        """
        调用 V3 模型根据大纲撰写正文，包含自审循环。
        Draft -> Anchor Check -> Critique -> Refine
        """
        if active_characters is None: active_characters = []

        print("✍️ Writer: 正在撰写初稿...")
        draft = self.write_chain.invoke({
            "outline": outline,
            "context_package": context_package
        })
        
        # 🔥 P1新增: 黄金锚点硬约束检查
        anchor_feedback = self._check_anchors(draft, active_characters)

        print("🤔 Writer: 正在自我审视...")
        critique = self.reflect_chain.invoke({
            "outline": outline,
            "draft": draft
        })
        
        # 整合反馈: 如果有锚点违规，强制附加到 Critique 中
        if anchor_feedback:
            critique += anchor_feedback
            # 强制标记为需要修改
            if "PASS" in critique:
                critique = critique.replace("PASS", "发现严重OOC问题，需重写")

        if "PASS" in critique and len(critique) < 20: # 稍微放宽长度检查，以免 PASS 后面有空格
            print("✅ Writer: 初稿通过自审。 ")
            return draft
        else:
            print(f"⚠️ Writer: 发现问题，正在修稿...\n   意见: {critique[:100]}...")
            final_version = self.refine_chain.invoke({
                "draft": draft,
                "critique": critique
            })
            return final_version