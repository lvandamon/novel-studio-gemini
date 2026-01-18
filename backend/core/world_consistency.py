"""
🌍 World Consistency Engine (世界一致性引擎)

功能:
1. 经济一致性 (Economy): 维护物价基准, 校验金钱消耗逻辑。
2. 地理一致性 (Travel): 维护地理坐标, 校验路程与时间逻辑。
3. 时间一致性 (Timeline): 维护世界历法, 确保时间流逝闭环。
"""

import math
import re
import sqlite3
from typing import List, Dict, Any, Optional
from core.memory import MemoryManager

class WorldConsistencyEngine:
    def __init__(self, memory_manager: MemoryManager):
        self.memory = memory_manager
        
        # 默认物价基准 (可由 init_world 覆盖)
        # 单位: 文 (Copper)
        self.price_baseline = {
            "烧饼": 2,
            "客栈住宿/晚": 50,
            "普通马匹": 5000,
            "上等宝剑": 50000,
            "一两白银": 1000,  # 1两银子 = 1000文
            "一两黄金": 10000  # 1两黄金 = 10两白银
        }
        
        # 旅行速度基准 (单位: 公里/天)
        self.travel_speeds = {
            "步行": 30,
            "普通马": 80,
            "千里马": 200,
            "御剑/飞行": 1000
        }

    # --- 经济一致性 ---

    def _cn_to_int(self, cn: str) -> int:
        """简单的中文数字转整数 (针对常见金额)"""
        mapping = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "百": 100, "千": 1000, "万": 10000}
        
        if cn.isdigit(): return int(cn)
        
        # 处理常见组合如 "一百", "一千"
        if len(cn) == 2 and cn[1] in ["十", "百", "千", "万"]:
            return mapping.get(cn[0], 1) * mapping.get(cn[1], 1)
        
        return mapping.get(cn, 1) # Fallback

    def validate_economy(self, draft: str, active_characters: List[str]) -> List[Dict]:
        """
        校验文中涉及的金钱数额是否与世界观设定冲突
        """
        violations = []
        
        # 匹配模式: (数字或中文数字) + (两|文|块) + (货币名)
        money_pattern = r'([0-9一二两三四五六七八九十百千万]+)\s*(两|文|块)\s*(银子|金子|灵石|白银|黄金)?'
        matches = re.finditer(money_pattern, draft)
        
        for match in matches:
            raw_amount = match.group(1)
            amount = self._cn_to_int(raw_amount)
            unit = match.group(2)
            currency = match.group(3) or "银子"
            
            # 严重逻辑崩坏: 10两金子 = 100两银子 = 10万文
            # 如果用 100两金子 买一个 2文钱的烧饼，那就是 500万倍的误差
            if unit == "两" and (currency in ["金子", "黄金"]) and amount >= 10:
                context = draft[max(0, match.start()-40) : min(len(draft), match.end()+40)]
                for low_value_item in ["烧饼", "馒头", "面条", "茶水"]:
                    if low_value_item in context:
                        violations.append({
                            "type": "ECONOMY_LOGIC_BREAK",
                            "severity": "ERROR",
                            "detail": f"经济逻辑崩坏: 文中描述使用 {raw_amount}{unit}{currency} 购买 {low_value_item} (约 {amount*10000} 文), 购买力与设定严重冲突。"
                        })
        
        return violations

    # --- 地理一致性 ---

    def validate_travel(self, draft: str, active_characters: List[str], current_chapter: int) -> List[Dict]:
        """
        校验位移逻辑。
        如果 A 城到 B 城距离 500 公里，文中描述"半天后到达"且无特殊交通工具 -> 违规。
        """
        violations = []
        # TODO: 从图谱中获取城市间距离 (需要 Neo4j 节点包含 coordinate)
        return violations

    # --- 时间一致性 ---

    def validate_timeline(self, draft: str, current_date_str: str, chapter_num: int) -> List[Dict]:
        """
        校验文中提到的时间点。
        解析 "三天后", "次日", "昨日" 等时间词汇，与系统记录的日期对比。
        """
        violations = []

        # 获取最近章节的时间记录
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()

        # 获取前一章的日期（如果存在）
        cursor.execute("""
            SELECT current_date FROM narrative_focus WHERE id = 1
        """)
        result = cursor.fetchone()
        previous_date = result[0] if result else current_date_str

        # 获取最近5章的事件时间记录（用于追踪时间流逝）
        cursor.execute("""
            SELECT chapter_num, description FROM events
            WHERE chapter_num >= ? AND chapter_num < ?
            ORDER BY chapter_num DESC LIMIT 20
        """, (max(1, chapter_num - 5), chapter_num))

        recent_events = cursor.fetchall()
        conn.close()

        # 时间词汇模式匹配
        time_patterns = {
            r'(昨[日天晚])': -1,  # 昨日、昨天、昨晚
            r'(今[日天晚])': 0,   # 今日、今天、今晚
            r'(明[日天晚])': 1,   # 明日、明天、明晚
            r'(次日|第二天)': 1,
            r'(三天[后後])': 3,
            r'(五天[后後])': 5,
            r'(七天[后後]|一周[后後])': 7,
            r'(十天[后後])': 10,
            r'(半月[后後]|十五天[后後])': 15,
            r'(一月[后後]|三十天[后後])': 30,
            r'(数月[后後])': 90,  # 假设"数月"为3个月
            r'(半年[后後])': 180,
            r'(一年[后後])': 365,
        }

        # 检测文中是否出现长时间跨越但没有合理过渡
        for pattern, days_delta in time_patterns.items():
            matches = re.finditer(pattern, draft)
            for match in matches:
                context = draft[max(0, match.start()-50):min(len(draft), match.end()+50)]

                # 严重违规：长时间跨越（超过30天）但无解释性过渡
                if days_delta >= 30:
                    # 检查是否有合理的时间流逝描述（如"闭关"、"修炼"、"养伤"）
                    transition_keywords = ["闭关", "修炼", "养伤", "疗伤", "静养", "潜修", "游历", "远行"]
                    has_transition = any(kw in context for kw in transition_keywords)

                    if not has_transition:
                        violations.append({
                            "type": "TIMELINE_JUMP_WARNING",
                            "severity": "WARNING",
                            "detail": f"时间线跳跃: 文中提到'{match.group(0)}'(约{days_delta}天), 但缺少合理的时间流逝过渡描述。建议添加'闭关'、'修炼'等解释性情节。",
                            "context": context
                        })

        # 检测矛盾的时间描述（例如："昨日刚到，今日已过三天"）
        time_mentions = []
        for pattern, days_delta in time_patterns.items():
            for match in re.finditer(pattern, draft):
                time_mentions.append({
                    "text": match.group(0),
                    "delta": days_delta,
                    "position": match.start()
                })

        # 如果同一章内出现多个时间点，检查逻辑一致性
        if len(time_mentions) >= 2:
            for i in range(len(time_mentions) - 1):
                curr = time_mentions[i]
                next_tm = time_mentions[i + 1]

                # 如果两个时间点都是确定的（非"数月"这种模糊描述），且矛盾
                if abs(curr["delta"]) <= 30 and abs(next_tm["delta"]) <= 30:
                    # 检测逻辑矛盾：例如先说"三天后"再说"昨日"
                    if curr["delta"] > 0 and next_tm["delta"] < 0:
                        violations.append({
                            "type": "TIMELINE_CONTRADICTION",
                            "severity": "ERROR",
                            "detail": f"时间线矛盾: 文中先提到'{curr['text']}'(+{curr['delta']}天), 后又提到'{next_tm['text']}'({next_tm['delta']}天), 逻辑冲突。"
                        })

        # 检测事件历史中的旅行时间矛盾
        # 例如："前一章在A城，本章说'昨日离开A城到达B城'，但A到B需要10天路程"
        travel_pattern = r'(从|离开)([^\s，。]{2,6})(到达|抵达|来到)([^\s，。]{2,6})'
        for match in re.finditer(travel_pattern, draft):
            departure = match.group(2)
            arrival = match.group(4)

            # 检查是否在近期时间词汇中出现（如"昨日到达"）
            context_window = draft[max(0, match.start()-30):min(len(draft), match.end()+30)]
            for pattern, days_delta in time_patterns.items():
                if re.search(pattern, context_window) and days_delta <= 1:
                    # 查询路线表（如果存在）
                    try:
                        conn = sqlite3.connect(self.memory.db_path)
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT distance_km FROM travel_routes
                            WHERE (departure = ? AND arrival = ?)
                            OR (departure = ? AND arrival = ?)
                        """, (departure, arrival, arrival, departure))
                        route = cursor.fetchone()
                        conn.close()

                        if route:
                            distance = route[0]
                            min_days = distance / self.travel_speeds["御剑/飞行"]  # 使用最快速度

                            if min_days > abs(days_delta) + 0.5:  # 留0.5天容差
                                violations.append({
                                    "type": "TRAVEL_TIME_IMPOSSIBLE",
                                    "severity": "ERROR",
                                    "detail": f"旅行时间矛盾: 从{departure}到{arrival}距离{distance}公里, 即使御剑飞行也需{min_days:.1f}天, 但文中描述为'{days_delta}天内到达', 物理上不可能。"
                                })
                    except:
                        pass  # 路线表不存在或查询失败，跳过

        return violations

    def generate_report(self, draft: str, active_characters: List[str], current_chapter: int, current_date: str = "天道历元年1月1日") -> List[Dict]:
        """聚合所有世界一致性检查"""
        all_violations = []
        all_violations.extend(self.validate_economy(draft, active_characters))
        all_violations.extend(self.validate_travel(draft, active_characters, current_chapter))
        all_violations.extend(self.validate_timeline(draft, current_date, current_chapter))
        return all_violations
