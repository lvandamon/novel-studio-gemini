from typing import Dict, Optional, Tuple, List
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
        
        # 移除硬编码地图，改为从 memory (SQLite) 读取
        # self.world_map = ... (Removed)

    def get_travel_options(self, origin: str, destination: str) -> Dict[str, str]:
        """
        获取两地之间的多种旅行方案。
        查询 SQL routes 表。
        """
        # 1. 尝试直接查找直达路线
        # 由于我们存储是有向图，但 `add_route` 并没有自动双向（我们在 init 里手动加了双向）
        # 所以直接查询 origin -> destination
        
        routes = self.memory.get_outbound_routes(origin)
        target_route = next((r for r in routes if r["target"] == destination), None)
        
        if not target_route:
            # 暂时不支持多跳路径规划 (Multi-hop pathfinding)
            # 如果需要，这里可以接入 Dijkstra 或 BFS，但目前仅返回 "无直达路线"
            return {}

        base_days = target_route["days"]
        methods_raw = target_route["methods"] # dict like {"Walk": "desc", ...}
        reqs = target_route["requirements"]
        
        options = {}
        
        # 格式化输出
        for mode, desc in methods_raw.items():
            cost_str = f"{desc}"
            # 如果有特殊要求，附加在描述里
            if reqs:
                cost_str += f" [需: {', '.join(reqs)}]"
            options[mode] = cost_str
             
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
        
        # 3. 旅行方案 (Dynamic DB Lookup)
        lines.append("\n## 可选旅行方案 (从当前位置出发)")
        lines.append("作者可根据剧情需要选择以下任一方式，但必须在文中体现对应的代价/条件：")
        
        # 获取当前地点的所有出口
        outbound = self.memory.get_outbound_routes(current_location)
        
        if outbound:
            for route in outbound:
                dest = route["target"]
                methods = route["methods"]
                lines.append(f"   > 去往【{dest}】:")
                for mode, desc in methods.items():
                    req_str = f" [需: {', '.join(route['requirements'])}]" if route['requirements'] else ""
                    lines.append(f"     - {mode}: {desc}{req_str}")
        else:
             # 获取地点描述
             loc_info = self.memory.get_location_info(current_location)
             desc = loc_info['description'] if loc_info else "未知区域"
             lines.append(f"- {current_location}: {desc} (当前无明确外连道路，请参考世界地图或自由发挥)")

        return "\n".join(lines)
