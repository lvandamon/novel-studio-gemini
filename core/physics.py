from typing import Dict, Optional, Tuple
from core.memory import MemoryManager
from datetime import datetime, timedelta

# 简单的自定义历法解析器
def parse_custom_date(date_str: str) -> Optional[Tuple[int, int, int]]:
    """解析 '天道历元年1月1日' 格式的日期"""
    try:
        # 去掉前缀
        parts = date_str.replace('天道历', '').split('年')
        year_str = parts[0]
        month_day = parts[1]
        
        # 解析年份
        year = int(year_str) if year_str != '元' else 1
        
        # 解析月日
        parts = month_day.split('月')
        month = int(parts[0])
        day = int(parts[1].replace('日', ''))
        
        return year, month, day
    except Exception:
        return None

def format_custom_date(year: int, month: int, day: int) -> str:
    """格式化为 '天道历元年1月1日'"""
    year_str = '元' if year == 1 else str(year)
    return f"天道历{year_str}年{month}月{day}日"

class PhysicalityEngine:
    """
    物理规则引擎 (Hard Logic Core)
    - 管理世界地图与旅行时间
    - 管理世界时钟
    """
    def __init__(self, memory_manager: MemoryManager):
        self.memory = memory_manager
        
        # 世界地图 (邻接表): {起点: {终点: 天数}}
        # 这是“绝对真理”，LLM 必须遵守
        self.world_map: Dict[str, Dict[str, int]] = {
            "新手村": {
                "青木城": 3,
                "黑石矿洞": 1
            },
            "青木城": {
                "新手村": 3,
                "天风城": 10,
                "云顶天宫": 30, # 飞行/传送
                "无尽之海港口": 15
            },
            "天风城": {
                "青木城": 10,
                "帝都": 25
            },
            "帝都": {
                "天风城": 25,
                "云顶天宫": 15
            },
            "云顶天宫": {
                 "帝都": 15,
                 "青木城": 30
            }
        }

    def get_travel_time(self, origin: str, destination: str) -> Optional[int]:
        """
        查询两地之间的旅行时间（天数）。
        这是单向的，如果需要双向，请确保在地图中定义。
        """
        if origin in self.world_map and destination in self.world_map[origin]:
            return self.world_map[origin][destination]
        # 尝试反向查询
        if destination in self.world_map and origin in self.world_map[destination]:
            return self.world_map[destination][origin]
        return None

    def advance_world_date(self, days_to_add: int) -> str:
        """
        推进世界日期，并持久化。
        """
        focus = self.memory.get_narrative_focus()
        current_date_str = focus.get("date", "天道历元年1月1日")
        
        # 使用标准库进行日期计算，假设每月30天，每年12个月
        # 注意：这里简化了历法，复杂的自定义历法需要更强的解析器
        try:
            # 这是一个简化的方法，不完全精确但能用
            parsed_date = parse_custom_date(current_date_str)
            if not parsed_date:
                # 如果解析失败，返回错误或默认值
                print(f"⚠️无法解析日期: {current_date_str}")
                return current_date_str

            year, month, day = parsed_date
            
            # 粗略计算
            day += days_to_add
            
            while day > 30:
                day -= 30
                month += 1
            
            while month > 12:
                month -= 12
                year += 1
                
            new_date_str = format_custom_date(year, month, day)

        except Exception as e:
            print(f"Error in date calculation: {e}")
            # 简单回退：直接在字符串上操作（不推荐）
            new_date_str = f"{current_date_str} (推进 {days_to_add} 天)"

        # 更新数据库
        self.memory.update_world_date(new_date_str)
        return new_date_str

    def get_hard_constraints_for_prompt(self, character_names: List[str], current_location: str) -> str:
        """
        为 Prompt 生成硬约束文本。
        """
        lines = ["# ⚙️ 物理法则 (Hard Constraints) - 必须严格遵守"]
        
        # 1. 当前日期
        current_date = self.memory.get_narrative_focus().get("date", "未知")
        lines.append(f"- 当前世界时间: {current_date}")

        # 2. 角色资产
        lines.append("\n## 资产状况")
        for name in character_names:
            char_data = self.memory.get_character(name)
            if char_data:
                gold = char_data.get("gold", 0)
                inventory = ", ".join(char_data.get("inventory", [])) or "空"
                lines.append(f"- {name}: [金币: {gold}] [物品: {inventory}]")
        
        # 3. 旅行时间
        lines.append("\n## 旅行时间 (从当前位置出发)")
        if current_location in self.world_map:
            for dest, time in self.world_map[current_location].items():
                lines.append(f"- {current_location} -> {dest}: {time} 天")
        else:
            lines.append(f"- {current_location} (未知地点，无精确旅行时间)")
            
        return "\n".join(lines)
