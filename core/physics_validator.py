"""
🔥 P1新增: 物理约束自动校验器 (Physics Constraint Validator)

功能:
1. 自动检测文本中的物理逻辑违规
2. 验证角色身体状态一致性
3. 验证物品状态合法性
4. 验证位置转移合理性

使用场景: Writer生成后、Reviewer审核时
"""

import re
from typing import List, Dict, Tuple
from core.memory import MemoryManager


class PhysicsViolation(Exception):
    """物理逻辑违规异常"""
    def __init__(self, violation_type: str, details: str, severity: str = "ERROR"):
        self.violation_type = violation_type
        self.details = details
        self.severity = severity
        super().__init__(f"[{severity}] {violation_type}: {details}")


class PhysicsValidator:
    """物理约束校验器"""

    def __init__(self, memory_manager: MemoryManager):
        self.memory = memory_manager

        # 身体部位关键词
        self.body_parts = {
            "左手": ["左手", "左臂", "左掌"],
            "右手": ["右手", "右臂", "右掌"],
            "左腿": ["左腿", "左脚", "左足"],
            "右腿": ["右腿", "右脚", "右足"],
            "双手": ["双手", "两手", "双臂"],
            "双腿": ["双腿", "两腿", "双足"],
            "眼睛": ["眼", "双眼", "目光", "视线"],
            "头": ["头", "脑袋"]
        }

        # 动作关键词映射
        self.action_patterns = {
            "手部动作": r"(持|握|抓|捏|按|推|拉|抚|摸|指|挥|舞|托)",
            "腿部动作": r"(走|跑|跳|踢|蹲|站|坐|跪)",
            "视觉动作": r"(看|望|瞧|瞥|凝视|注视|盯)",
            "双手动作": r"(双手|两手).{0,3}(持|握|抓|托|推|拉)"
        }

    def validate_draft(self, draft: str, active_characters: List[str], chapter_num: int) -> List[Dict]:
        """
        验证草稿的物理一致性

        Returns:
            List[Dict]: 违规列表 [{"type": str, "severity": str, "detail": str}, ...]
        """
        violations = []

        for char_name in active_characters:
            char_violations = self._validate_character_physics(draft, char_name, chapter_num)
            violations.extend(char_violations)

        return violations

    def _validate_character_physics(self, draft: str, char_name: str, chapter_num: int) -> List[Dict]:
        """验证单个角色的物理状态"""
        violations = []

        # 获取角色物理状态
        char = self.memory.get_character(char_name)
        if not char:
            return violations

        body_status = char.get('body_status', [])

        # 1. 检查断肢违规
        severed_parts = [p for p in body_status if p.get('is_severed')]
        for part in severed_parts:
            part_name = part['name']
            # 检查文本中是否违规使用该部位
            violation = self._check_severed_limb_usage(draft, char_name, part_name)
            if violation:
                violations.append(violation)

        # 2. 检查残废部位违规
        crippled_parts = [p for p in body_status if p.get('is_crippled')]
        for part in crippled_parts:
            part_name = part['name']
            violation = self._check_crippled_limb_usage(draft, char_name, part_name)
            if violation:
                violations.append(violation)

        # 3. 检查双手/双腿动作(当有单侧缺失时)
        if severed_parts or crippled_parts:
            violation = self._check_bilateral_actions(draft, char_name, severed_parts + crippled_parts)
            if violation:
                violations.append(violation)

        return violations

    def _check_severed_limb_usage(self, draft: str, char_name: str, part_name: str) -> Dict | None:
        """检查断肢使用违规"""
        # 查找角色相关的段落
        char_contexts = self._extract_character_contexts(draft, char_name)

        for context in char_contexts:
            # 检查是否提及该部位
            keywords = self.body_parts.get(part_name, [part_name])
            for keyword in keywords:
                if keyword in context:
                    # 进一步检查是否在执行动作
                    for action_type, pattern in self.action_patterns.items():
                        if re.search(f"{keyword}.{{0,5}}{pattern}", context) or \
                           re.search(f"{pattern}.{{0,5}}{keyword}", context):
                            return {
                                "type": "SEVERED_LIMB_USAGE",
                                "severity": "CRITICAL",
                                "character": char_name,
                                "detail": f"{char_name}的{part_name}已缺失,但文中描述了使用该部位的动作: {context[:50]}..."
                            }
        return None

    def _check_crippled_limb_usage(self, draft: str, char_name: str, part_name: str) -> Dict | None:
        """检查残废部位过度使用"""
        char_contexts = self._extract_character_contexts(draft, char_name)

        for context in char_contexts:
            keywords = self.body_parts.get(part_name, [part_name])
            for keyword in keywords:
                # 残废部位可以提及,但不能执行复杂/剧烈动作
                forbidden_actions = r"(挥舞|舞动|重击|猛|狠|奋力|拼命).{0,3}" + keyword
                if re.search(forbidden_actions, context):
                    return {
                        "type": "CRIPPLED_LIMB_OVERUSE",
                        "severity": "WARNING",
                        "character": char_name,
                        "detail": f"{char_name}的{part_name}已残废,但文中描述了剧烈动作: {context[:50]}..."
                    }
        return None

    def _check_bilateral_actions(self, draft: str, char_name: str, damaged_parts: List[Dict]) -> Dict | None:
        """检查双侧动作(当单侧损坏时)"""
        # 检查是否有手或腿的单侧损伤
        left_hand_damaged = any(p['name'] in ['左手', '左臂'] for p in damaged_parts)
        right_hand_damaged = any(p['name'] in ['右手', '右臂'] for p in damaged_parts)
        left_leg_damaged = any(p['name'] in ['左腿', '左脚'] for p in damaged_parts)
        right_leg_damaged = any(p['name'] in ['右腿', '右脚'] for p in damaged_parts)

        char_contexts = self._extract_character_contexts(draft, char_name)

        for context in char_contexts:
            # 检查双手动作
            if (left_hand_damaged or right_hand_damaged):
                if re.search(self.action_patterns["双手动作"], context):
                    damaged_side = "左" if left_hand_damaged else "右"
                    return {
                        "type": "BILATERAL_ACTION_VIOLATION",
                        "severity": "ERROR",
                        "character": char_name,
                        "detail": f"{char_name}的{damaged_side}手已损伤,但文中使用了'双手'动作: {context[:50]}..."
                    }

            # 检查双腿动作(如跳跃、奔跑等)
            if (left_leg_damaged or right_leg_damaged):
                bilateral_leg_actions = r"(跳跃|奔跑|飞奔|健步|大步)"
                if re.search(bilateral_leg_actions, context):
                    damaged_side = "左" if left_leg_damaged else "右"
                    return {
                        "type": "BILATERAL_ACTION_VIOLATION",
                        "severity": "ERROR",
                        "character": char_name,
                        "detail": f"{char_name}的{damaged_side}腿已损伤,但文中进行了需要双腿的剧烈动作: {context[:50]}..."
                    }

        return None

    def _extract_character_contexts(self, text: str, char_name: str, context_window: int = 50) -> List[str]:
        """提取角色相关的上下文片段"""
        contexts = []
        # 找到所有提及该角色的位置
        for match in re.finditer(char_name, text):
            start = max(0, match.start() - context_window)
            end = min(len(text), match.end() + context_window)
            contexts.append(text[start:end])
        return contexts

    def validate_item_usage(self, draft: str, char_name: str, item_name: str) -> Dict | None:
        """
        验证物品使用合法性

        检查:
        1. 物品是否在角色背包中
        2. 物品耐久度是否为0
        3. 物品状态是否允许使用
        """
        char = self.memory.get_character(char_name)
        if not char:
            return None

        inventory = char.get('inventory', [])

        # 查找物品
        item = None
        for inv_item in inventory:
            if isinstance(inv_item, dict) and inv_item.get('name') == item_name:
                item = inv_item
                break

        if not item:
            # 角色没有该物品
            if item_name in draft and char_name in draft:
                return {
                    "type": "ITEM_NOT_OWNED",
                    "severity": "ERROR",
                    "character": char_name,
                    "detail": f"{char_name}使用了不在背包中的物品: {item_name}"
                }
            return None

        # 检查耐久度
        if item.get('durability', 100) <= 0:
            if item_name in draft:
                return {
                    "type": "BROKEN_ITEM_USAGE",
                    "severity": "ERROR",
                    "character": char_name,
                    "detail": f"{char_name}使用了已损毁的物品: {item_name}"
                }

        return None

    def generate_validation_report(self, violations: List[Dict]) -> str:
        """生成可读的验证报告"""
        if not violations:
            return "✅ 物理约束验证通过: 未发现逻辑违规"

        report_lines = [f"❌ 发现 {len(violations)} 个物理逻辑违规:\n"]

        # 按严重性分组
        critical = [v for v in violations if v['severity'] == 'CRITICAL']
        errors = [v for v in violations if v['severity'] == 'ERROR']
        warnings = [v for v in violations if v['severity'] == 'WARNING']

        if critical:
            report_lines.append("🔴 致命违规 (CRITICAL):")
            for v in critical:
                report_lines.append(f"  - {v['detail']}")

        if errors:
            report_lines.append("\n🟠 严重违规 (ERROR):")
            for v in errors:
                report_lines.append(f"  - {v['detail']}")

        if warnings:
            report_lines.append("\n🟡 警告 (WARNING):")
            for v in warnings:
                report_lines.append(f"  - {v['detail']}")

        return "\n".join(report_lines)
