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
    """
    🔥 P3升级: 物理约束校验器 - 扩展词库版

    新增:
    1. 更全面的身体部位同义词
    2. 更丰富的动作词库(武侠/仙侠常用词)
    3. 上下文排除规则(避免误判)
    """

    def __init__(self, memory_manager: MemoryManager):
        self.memory = memory_manager

        # 🔥 P3升级: 扩展身体部位关键词 (增加武侠/仙侠常用词)
        self.body_parts = {
            # 手臂相关
            "左手": ["左手", "左臂", "左掌", "左拳", "左腕", "左肩", "左袖"],
            "右手": ["右手", "右臂", "右掌", "右拳", "右腕", "右肩", "右袖"],
            "双手": ["双手", "两手", "双臂", "双掌", "双拳", "十指", "双腕"],

            # 腿脚相关
            "左腿": ["左腿", "左脚", "左足", "左膝", "左踝", "左胯"],
            "右腿": ["右腿", "右脚", "右足", "右膝", "右踝", "右胯"],
            "双腿": ["双腿", "两腿", "双足", "双脚", "双膝"],

            # 感官相关
            "眼睛": ["眼", "双眼", "目光", "视线", "眼眸", "瞳孔", "左眼", "右眼", "眸子", "眼帘"],
            "耳朵": ["耳", "双耳", "耳畔", "左耳", "右耳"],

            # 其他重要部位
            "头": ["头", "脑袋", "头颅", "颅", "脑"],
            "丹田": ["丹田", "气海", "下丹田"],
            "经脉": ["经脉", "脉络", "气脉", "任督"],
            "神识": ["神识", "精神力", "神念", "意识"]
        }

        # 🔥 P3升级: 扩展动作关键词映射 (武侠/仙侠专用)
        self.action_patterns = {
            # 手部基础动作
            "手部动作": r"(持|握|抓|捏|按|推|拉|抚|摸|指|挥|舞|托|提|举|端|捧|抱|撑|拍|打|劈|砍|刺|斩|扫|削|点|戳|弹|拨|扣|接|挡|招架|格挡)",

            # 手部武术动作
            "手部武术动作": r"(运功|催动|施展|出掌|挥拳|剑指|御剑|凝聚|汇聚|注入真气|灌入灵力|施法|结印|掐诀)",

            # 腿部基础动作
            "腿部动作": r"(走|跑|跳|踢|蹲|站|坐|跪|爬|迈|踏|踩|奔|冲|跨|跃|纵|闪|躲|退)",

            # 腿部武术动作
            "腿部武术动作": r"(纵身|腾空|飞身|闪身|跃起|一跃|蹬地|踏空|凌空|御风|御剑飞行|急退|横移|飘落)",

            # 视觉动作
            "视觉动作": r"(看|望|瞧|瞥|凝视|注视|盯|扫视|环顾|目视|眺望|俯视|仰望|端详|打量|审视|观察|察看|窥视|洞察|神识探查)",

            # 听觉动作
            "听觉动作": r"(听|倾听|聆听|侧耳|谛听|捕捉到)",

            # 双手协同动作
            "双手动作": r"(双手|两手|双臂|双掌|十指).{0,5}(持|握|抓|托|推|拉|合|分|挥|施展|运转|凝聚|环抱|合十|结印)",

            # 双腿协同动作
            "双腿动作": r"(双腿|两腿|双足).{0,5}(并|分|站|踏|跳|蹲|跃|纵)"
        }

        # 🔥 P3新增 + P4升级: 排除规则 (这些情况不算违规)
        self.exclusion_patterns = {
            # 回忆/描述过去的情况
            "回忆": r"(曾经|以前|往日|昔日|当初|想起|记得|回想|那时|当年|年前|从前)",
            # 幻觉/梦境
            "幻觉": r"(幻觉|幻象|幻影|梦中|梦里|恍惚间|仿佛|好像|似乎|像是|如同|宛如)",
            # 他人视角描述
            "旁白": r"(他的|她的|其).{0,3}(左手|右手|双手|左腿|右腿)",
            # 疗伤/恢复描述
            "恢复": r"(治愈|痊愈|恢复|再生|重生|接回|续上|治好|医好)",
            # 🔥 P4新增: 假设/比喻语境
            "假设": r"(如果|假如|若是|倘若|要是|本可以|原本能|本来可以)",
            # 🔥 P4新增: 否定语境
            "否定": r"(再也不能|无法|不能|做不到|失去了|没了)",
            # 🔥 P4新增: 他人代劳
            "代劳": r"(帮.{0,4}(持|握|拿|扶)|替.{0,4}(持|握|拿|扶)|搀扶)"
        }

        # 🔥 P4新增: 上下文窗口扩展 (用于深度分析)
        self.extended_context_window = 100  # 扩展上下文窗口
        self.sentence_delimiters = r'[。！？.!?\n]'  # 句子分隔符

        # 🔥 P3新增: 严重动作词库 (残废部位绝对不能做的)
        self.severe_actions = {
            "手部": r"(挥舞|舞动|重击|猛击|狠砸|奋力|拼命|全力|竭力|死死|紧紧).{0,5}(持|握|抓|挥|打|劈|砍|刺)",
            "腿部": r"(狂奔|疾跑|全速|拼命|竭力|奋力).{0,5}(跑|奔|跃|冲|踢)",
            "眼部": r"(死死|紧紧|目不转睛|一眨不眨).{0,5}(盯|注视|凝视|望)"
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

    def _should_exclude_context(self, context: str) -> bool:
        """
        🔥 P3新增 + P4升级: 检查上下文是否应该排除 (回忆/幻觉/旁白等)

        P4升级: 增加上下文深度分析,不仅检查当前句,还检查前后句
        """
        for excl_type, pattern in self.exclusion_patterns.items():
            if re.search(pattern, context):
                return True
        return False

    def _get_sentence_context(self, text: str, position: int) -> str:
        """
        🔥 P4新增: 获取完整的句子上下文

        Args:
            text: 完整文本
            position: 关键词位置

        Returns:
            包含该位置的完整句子
        """
        # 向前查找句子起点
        start = position
        while start > 0 and not re.match(self.sentence_delimiters, text[start-1]):
            start -= 1

        # 向后查找句子终点
        end = position
        while end < len(text) and not re.match(self.sentence_delimiters, text[end]):
            end += 1

        return text[max(0, start-20):min(len(text), end+20)]

    def _analyze_subject(self, context: str, char_name: str, part_keywords: List[str]) -> bool:
        """
        🔥 P4新增: 分析动作主语是否为指定角色

        检查动作描述中的部位是否属于当前角色,还是在描述他人

        Returns:
            True = 动作主语是当前角色 (需要检查违规)
            False = 动作主语是其他人 (不算违规)
        """
        # 检查是否有明确的他人代词在部位前
        other_possessive = [
            r'他的.{0,3}(' + '|'.join(part_keywords) + ')',
            r'她的.{0,3}(' + '|'.join(part_keywords) + ')',
            r'其.{0,3}(' + '|'.join(part_keywords) + ')',
            r'对方的.{0,3}(' + '|'.join(part_keywords) + ')',
            r'敌人的.{0,3}(' + '|'.join(part_keywords) + ')',
        ]

        for pattern in other_possessive:
            if re.search(pattern, context):
                return False  # 是在描述他人

        # 检查是否有明确的角色名在部位前 (且不是当前角色)
        # 例如: "张三的左手" (当char_name != "张三"时不算违规)
        name_pattern = r'[\u4e00-\u9fa5]{2,4}的.{0,3}(' + '|'.join(part_keywords) + ')'
        matches = re.findall(name_pattern, context)
        for match in matches:
            # 提取名字
            name_match = re.search(r'([\u4e00-\u9fa5]{2,4})的', context)
            if name_match:
                mentioned_name = name_match.group(1)
                if mentioned_name != char_name and mentioned_name not in char_name:
                    return False  # 是在描述其他角色

        return True  # 默认认为是当前角色

    def _check_severed_limb_usage(self, draft: str, char_name: str, part_name: str) -> Dict | None:
        """
        🔥 P3升级 + P4升级: 检查断肢使用违规 (增加排除规则 + 主语分析)
        """
        char_contexts = self._extract_character_contexts(draft, char_name, context_window=self.extended_context_window)

        keywords = self.body_parts.get(part_name, [part_name])

        for context in char_contexts:
            # 🔥 P3新增: 排除回忆/幻觉等场景
            if self._should_exclude_context(context):
                continue

            for keyword in keywords:
                if keyword in context:
                    # 🔥 P4新增: 分析动作主语
                    if not self._analyze_subject(context, char_name, keywords):
                        continue  # 不是当前角色的动作

                    # 检查所有动作类型
                    for action_type, pattern in self.action_patterns.items():
                        # 检测动作模式
                        if re.search(f"{keyword}.{{0,8}}{pattern}", context) or \
                           re.search(f"{pattern}.{{0,8}}{keyword}", context):

                            # 🔥 P4新增: 二次确认 - 扩展上下文再检查一次排除规则
                            keyword_pos = context.find(keyword)
                            if keyword_pos >= 0:
                                extended_ctx = self._get_sentence_context(draft, draft.find(context[:30]) + keyword_pos if context[:30] in draft else 0)
                                if self._should_exclude_context(extended_ctx):
                                    continue

                            return {
                                "type": "SEVERED_LIMB_USAGE",
                                "severity": "CRITICAL",
                                "character": char_name,
                                "detail": f"{char_name}的{part_name}已缺失,但文中描述了使用该部位的动作({action_type}): {context[:60]}..."
                            }
        return None

    def _check_crippled_limb_usage(self, draft: str, char_name: str, part_name: str) -> Dict | None:
        """
        🔥 P3升级: 检查残废部位过度使用 (使用扩展严重动作词库)
        """
        char_contexts = self._extract_character_contexts(draft, char_name)

        for context in char_contexts:
            # 排除回忆/幻觉等场景
            if self._should_exclude_context(context):
                continue

            keywords = self.body_parts.get(part_name, [part_name])

            # 🔥 P3升级: 根据部位类型选择对应的严重动作检测
            severe_pattern = None
            if "手" in part_name or "臂" in part_name or "掌" in part_name:
                severe_pattern = self.severe_actions["手部"]
            elif "腿" in part_name or "脚" in part_name or "足" in part_name:
                severe_pattern = self.severe_actions["腿部"]
            elif "眼" in part_name:
                severe_pattern = self.severe_actions["眼部"]

            for keyword in keywords:
                if keyword in context:
                    # 使用对应类型的严重动作检测
                    if severe_pattern and re.search(severe_pattern, context):
                        return {
                            "type": "CRIPPLED_LIMB_OVERUSE",
                            "severity": "WARNING",
                            "character": char_name,
                            "detail": f"{char_name}的{part_name}已残废,但文中描述了剧烈动作: {context[:60]}..."
                        }

                    # 后备: 通用剧烈动作检测
                    fallback_pattern = r"(挥舞|舞动|重击|猛|狠|奋力|拼命|全力|竭力).{0,5}" + keyword
                    if re.search(fallback_pattern, context):
                        return {
                            "type": "CRIPPLED_LIMB_OVERUSE",
                            "severity": "WARNING",
                            "character": char_name,
                            "detail": f"{char_name}的{part_name}已残废,但文中描述了剧烈动作: {context[:60]}..."
                        }
        return None

    def _check_bilateral_actions(self, draft: str, char_name: str, damaged_parts: List[Dict]) -> Dict | None:
        """
        🔥 P3升级: 检查双侧动作 (扩展检测范围)
        """
        # 检查是否有手或腿的单侧损伤 (扩展部位名称)
        hand_parts = ['左手', '左臂', '左掌', '左拳', '左腕']
        right_hand_parts = ['右手', '右臂', '右掌', '右拳', '右腕']
        left_leg_parts = ['左腿', '左脚', '左足', '左膝']
        right_leg_parts = ['右腿', '右脚', '右足', '右膝']

        left_hand_damaged = any(p['name'] in hand_parts for p in damaged_parts)
        right_hand_damaged = any(p['name'] in right_hand_parts for p in damaged_parts)
        left_leg_damaged = any(p['name'] in left_leg_parts for p in damaged_parts)
        right_leg_damaged = any(p['name'] in right_leg_parts for p in damaged_parts)

        char_contexts = self._extract_character_contexts(draft, char_name)

        for context in char_contexts:
            # 排除回忆/幻觉等场景
            if self._should_exclude_context(context):
                continue

            # 检查双手动作
            if left_hand_damaged or right_hand_damaged:
                if re.search(self.action_patterns["双手动作"], context):
                    damaged_side = "左" if left_hand_damaged else "右"
                    return {
                        "type": "BILATERAL_ACTION_VIOLATION",
                        "severity": "ERROR",
                        "character": char_name,
                        "detail": f"{char_name}的{damaged_side}手已损伤,但文中使用了'双手'动作: {context[:60]}..."
                    }

            # 🔥 P3升级: 扩展双腿动作检测
            if left_leg_damaged or right_leg_damaged:
                # 扩展的双腿动作词库
                bilateral_leg_actions = r"(跳跃|奔跑|飞奔|健步|大步|疾驰|纵跃|腾空|凌空|御风飞行|踏空|飞身|全速奔跑|急速冲刺)"
                if re.search(bilateral_leg_actions, context):
                    damaged_side = "左" if left_leg_damaged else "右"
                    return {
                        "type": "BILATERAL_ACTION_VIOLATION",
                        "severity": "ERROR",
                        "character": char_name,
                        "detail": f"{char_name}的{damaged_side}腿已损伤,但文中进行了需要双腿的动作: {context[:60]}..."
                    }

                # 检查双腿协同动作
                if re.search(self.action_patterns.get("双腿动作", ""), context):
                    damaged_side = "左" if left_leg_damaged else "右"
                    return {
                        "type": "BILATERAL_ACTION_VIOLATION",
                        "severity": "ERROR",
                        "character": char_name,
                        "detail": f"{char_name}的{damaged_side}腿已损伤,但文中进行了双腿协同动作: {context[:60]}..."
                    }

        return None

    def _extract_character_contexts(self, text: str, char_name: str, context_window: int = 50) -> List[str]:
        """
        🔥 P4升级: 提取角色相关的上下文片段

        改进:
        1. 支持可配置的上下文窗口
        2. 尝试扩展到完整句子边界
        3. 去重处理
        """
        contexts = []
        seen = set()

        # 找到所有提及该角色的位置
        for match in re.finditer(re.escape(char_name), text):
            # 基础窗口
            start = max(0, match.start() - context_window)
            end = min(len(text), match.end() + context_window)

            # 尝试扩展到句子边界
            while start > 0 and text[start] not in '。！？.!?\n' and (match.start() - start) < context_window * 1.5:
                start -= 1
            while end < len(text) and text[end-1] not in '。！？.!?\n' and (end - match.end()) < context_window * 1.5:
                end += 1

            context = text[start:end]

            # 去重
            context_key = context[:50]
            if context_key not in seen:
                seen.add(context_key)
                contexts.append(context)

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
