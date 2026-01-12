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

    def get_travel_options(self, origin: str, destination: str) -> Dict[str, str]:
        """
        获取两地之间的多种旅行方案。
        返回格式: {"Walk": "30天 (无消耗)", "Fly": "6天 (需筑基期)", "Teleport": "瞬达 (需100灵石)"}
        """
        base_days = None
        
        # 查找基础时间
        if origin in self.world_map and destination in self.world_map[origin]:
            base_days = self.world_map[origin][destination]
        elif destination in self.world_map and origin in self.world_map[destination]:
            base_days = self.world_map[destination][origin]
            
        if base_days is None:
            return {}

        options = {}
        
        # 1. 步行 (Base)
        options["步行 (Walk)"] = f"{base_days} 天 (无消耗)"
        
        # 2. 御剑/飞行 (Fly) - 假设 5x 速度
        fly_days = max(1, base_days // 5)
        options["御剑/飞行 (Fly)"] = f"{fly_days} 天 (条件: 境界>=筑基 或 飞行法宝)"
        
        # 3. 传送 (Teleport) - 瞬达
        # 只有大城市才有传送阵 (这里简单判定：只要基础距离 > 10天，假设有传送需求)
        if base_days >= 10:
             options["传送阵 (Teleport)"] = "即刻到达 (消耗: 100 金币/灵石)"
             
        return options

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
                level = char_data.get("level", "凡人")
                lines.append(f"- {name}: [境界: {level}] [金币: {gold}] [物品: {inventory}]")
        
        # 3. 旅行方案
        lines.append("\n## 可选旅行方案 (从当前位置出发)")
        lines.append("作者可根据剧情需要选择以下任一方式，但必须在文中体现对应的代价/条件：")
        
        found_routes = False
        if current_location in self.world_map:
            for dest in self.world_map[current_location].keys():
                opts = self.get_travel_options(current_location, dest)
                if opts:
                    found_routes = True
                    lines.append(f"   > 去往【{dest}】:")
                    for mode, desc in opts.items():
                        lines.append(f"     - {mode}: {desc}")
        
        if not found_routes:
             # 尝试反向查找作为补充提示
             lines.append(f"- {current_location} (当前无明确外连道路，请参考世界地图或自由发挥，但需遵循逻辑)")

        return "\n".join(lines)
