import json
import re
from typing import Dict, Any, List
from langchain_core.output_parsers import StrOutputParser
from core.llm import get_deepseek_reasoner
from core.prompts import EDITOR_GEN_OUTLINE_PROMPT
from core.context_manager import ContextManager
from core.schemas import AtmosphereSchema

class EditorAgent:
    def __init__(self, context_manager: ContextManager):
        # Editor use Reasoner (R1) for logical plot planning
        self.llm = get_deepseek_reasoner()
        self.chain = EDITOR_GEN_OUTLINE_PROMPT | self.llm | StrOutputParser()
        self.context_manager = context_manager
        self.memory = context_manager.memory

    def _pre_validate_physics(self, active_characters: List[str], outline_text: str) -> Dict[str, Any]:
        """
        🔥 P8新增: 物理约束前置检查

        在大纲生成后、Simulator检查前进行轻量级物理可行性预检
        检测明显的物理违规（如断肢角色执行双手动作）

        Returns:
            Dict with 'passed', 'warnings', 'blockers'
        """
        warnings = []
        blockers = []

        for char_name in active_characters:
            char = self.memory.get_character(char_name)
            if not char:
                continue

            body_status = char.get('body_status', [])

            # 检查断肢
            severed_parts = [p for p in body_status if p.get('is_severed')]
            crippled_parts = [p for p in body_status if p.get('is_crippled')]

            for part in severed_parts:
                part_name = part['name']

                # 检查大纲中是否有使用该部位的描述
                # 手部检测
                if '手' in part_name or '臂' in part_name:
                    if re.search(r'(双手|两手|双臂).{0,10}(持|握|挥|打|施展|运功)', outline_text):
                        blockers.append({
                            "character": char_name,
                            "part": part_name,
                            "issue": f"{char_name}的{part_name}已缺失，但大纲中有双手动作",
                            "severity": "CRITICAL"
                        })
                    if re.search(f'{part_name}.{{0,10}}(持|握|挥|打|施展)', outline_text):
                        blockers.append({
                            "character": char_name,
                            "part": part_name,
                            "issue": f"{char_name}的{part_name}已缺失，但大纲中使用该部位",
                            "severity": "CRITICAL"
                        })

                # 腿部检测
                if '腿' in part_name or '脚' in part_name:
                    if re.search(r'(奔跑|跳跃|飞身|健步|纵跃|踏空)', outline_text):
                        blockers.append({
                            "character": char_name,
                            "part": part_name,
                            "issue": f"{char_name}的{part_name}已缺失，但大纲中有双腿动作",
                            "severity": "CRITICAL"
                        })

            # 检查残废部位的剧烈动作
            for part in crippled_parts:
                part_name = part['name']
                if '手' in part_name and re.search(r'(奋力|拼命|全力).{0,5}(挥|打|砍|劈)', outline_text):
                    warnings.append({
                        "character": char_name,
                        "part": part_name,
                        "issue": f"{char_name}的{part_name}已残废，建议避免剧烈动作描写",
                        "severity": "WARNING"
                    })

        passed = len(blockers) == 0

        if blockers:
            print(f"   🚨 P8物理前置检查: 发现 {len(blockers)} 个致命违规!")
            for b in blockers:
                print(f"      - [{b['severity']}] {b['issue']}")

        if warnings:
            print(f"   ⚠️ P8物理前置检查: 发现 {len(warnings)} 个警告")

        return {
            "passed": passed,
            "warnings": warnings,
            "blockers": blockers,
            "total_issues": len(warnings) + len(blockers)
        }

    def _get_causal_context(self, active_characters: list) -> str:
        """从图谱中提取关键角色的因果链背景"""
        if not self.memory.graph.is_connected() or not active_characters:
            return ""
        
        causal_report = ["### 🕸️ 因果链追溯 (Causal Context)"]
        for char in active_characters:
            # 1. 查询角色的社交/状态关系
            rel_context = self.memory.graph.query_entity_context(char)
            if "暂无" not in rel_context:
                causal_report.append(f"【{char} 的既定关系】:\n{rel_context}")
            
            # 2. 尝试寻找因果链 (这里可以根据需要扩展，比如查找最近参与的重大事件)
            # 暂时使用 entity_context 提供的关系作为基础，
            # 也可以在这里增加特定的因果追溯逻辑。
        
        return "\n".join(causal_report) if len(causal_report) > 1 else ""

    def _clean_json(self, text: str) -> str:
        """
        针对 Reasoner 模型的鲁棒 JSON 提取器
        1. 移除 <think> 思考过程
        2. 提取 markdown json 块
        3. 兜底提取 {}
        """
        # 1. 移除 <think> 标签及其内容 (非贪婪匹配)
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        
        # 2. 尝试匹配 ```json ... ```
        match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            return match.group(1)
            
        # 3. 尝试匹配最外层的 {}
        match = re.search(r'(\{.*\})', text, re.DOTALL)
        if match:
            return match.group(1)
            
        return text.strip()

    def generate_outline(self, chapter_num: int, context_package: str, causal_context: str = "", max_physics_retries: int = 2) -> Dict[str, Any]:
        """
        调用 R1 模型生成章节大纲，并进行格式清洗和补全。

        🔥 P8升级: 集成物理约束前置检查，在大纲阶段就拦截明显的物理违规
        """
        print(f"🧠 Editor: 正在构思第 {chapter_num} 章大纲 (DeepSeek-R1)...")

        full_context = context_package
        if causal_context:
            full_context += f"\n\n{causal_context}"

        physics_retry_count = 0

        while physics_retry_count <= max_physics_retries:
            try:
                # 如果是重试，添加物理约束提示
                retry_context = full_context
                if physics_retry_count > 0:
                    retry_context += "\n\n⚠️ 【物理约束提醒】上一版大纲存在物理违规，请特别注意角色的身体状态限制！"

                raw_output = self.chain.invoke({
                    "context": retry_context,
                    "chapter_num": chapter_num
                })

                cleaned_json = self._clean_json(raw_output)
                data = json.loads(cleaned_json)

                # --- 字段完整性校验与补全 ---

                # 1. Title
                if "title" not in data:
                    data["title"] = f"第 {chapter_num} 章"

                # 1.5 Estimated Duration (New)
                if "estimated_duration" not in data:
                    data["estimated_duration"] = "未知"

                # 2. Outline (标准化为 List[str])
                if "outline" not in data:
                    data["outline"] = ["本章大纲生成失败，请人工核查。"]
                elif isinstance(data["outline"], str):
                    # 如果模型偷懒只返回了字符串，尝试按行分割
                    data["outline"] = [line.strip() for line in data["outline"].split('\n') if line.strip()]

                # 3. Active Characters
                if "active_characters" not in data:
                    data["active_characters"] = []

                # 4. Scene Location
                if "scene_location" not in data:
                    data["scene_location"] = "未知地点"

                # 5. Atmosphere (确保是 Dict)
                if "atmosphere" not in data or not isinstance(data["atmosphere"], dict):
                    data["atmosphere"] = {
                        "tone": "正常",
                        "sensory_focus": "视觉",
                        "color_palette": "正常"
                    }

                # 🔥 P8新增: 物理约束前置检查
                if data["active_characters"]:
                    outline_text = "\n".join(data["outline"]) if isinstance(data["outline"], list) else str(data["outline"])
                    physics_check = self._pre_validate_physics(data["active_characters"], outline_text)

                    if not physics_check["passed"]:
                        physics_retry_count += 1
                        if physics_retry_count <= max_physics_retries:
                            print(f"   🔄 物理前置检查未通过，重新生成大纲 (尝试 {physics_retry_count}/{max_physics_retries})...")
                            # 将违规信息添加到上下文
                            violation_info = "\n".join([f"- {b['issue']}" for b in physics_check["blockers"]])
                            full_context += f"\n\n🚨 【必须修正的物理违规】:\n{violation_info}"
                            continue
                        else:
                            # 达到最大重试次数，添加警告但继续
                            data["physics_warnings"] = physics_check["blockers"]
                            print(f"   ⚠️ 物理前置检查仍未通过，已达最大重试次数，交由Simulator处理")

                print(f"   ✅ 大纲生成完毕: 《{data['title']}》- 共 {len(data['outline'])} 个节点")
                return data

            except json.JSONDecodeError:
                print(f"   ⚠️ Editor JSON 解析失败。Raw output:\n{raw_output[:200]}...")
                return {
                    "title": f"第 {chapter_num} 章 (解析错误)",
                    "outline": ["大纲生成数据格式错误，请检查日志。"],
                    "active_characters": [],
                    "scene_location": "未知",
                    "atmosphere": {},
                    "error": "JSON Parse Error"
                }
            except Exception as e:
                print(f"   ⚠️ Editor 运行错误: {e}")
                return {
                    "title": "错误",
                    "outline": [f"系统错误: {str(e)}"],
                    "active_characters": [],
                    "scene_location": "未知",
                    "atmosphere": {}
                }

        # 如果循环结束仍未返回（不应该发生）
        return {
            "title": f"第 {chapter_num} 章",
            "outline": ["大纲生成超时，请重试。"],
            "active_characters": [],
            "scene_location": "未知",
            "atmosphere": {}
        }