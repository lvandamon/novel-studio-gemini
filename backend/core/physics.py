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
        为 Prompt 生成硬约束文本 (Hard Constraints)。
        包含：时间、金钱、物品(带状态)、生理残疾(Critical)、当前Buff/Debuff。
        """
        lines = ["# ⚙️ 物理法则 (Hard Constraints) - 必须严格遵守"]
        
        # 1. 当前日期
        current_date = self.memory.get_narrative_focus().get("date", "未知")
        lines.append(f"- 当前世界时间: {current_date}")

        # 2. 角色硬状态 (Hard State)
        lines.append("\n## 👥 角色生理与资产状态 (Physiology & Assets)")
        for name in character_names:
            char_data = self.memory.get_character(name)
            if not char_data: continue
            
            level = char_data.get("level", "凡人")
            gold = char_data.get("gold", 0)
            
            # Header
            lines.append(f"### {name} [Level: {level}] [Gold: {gold}]")
            
            # A. Critical Body Status (残疾/损伤)
            body_status = char_data.get("body_status", [])
            has_critical = False
            for part in body_status:
                status_tags = []
                if part.get("is_severed"): status_tags.append("❌缺失/SEVERED")
                if part.get("is_crippled"): status_tags.append("⚠️残废/CRIPPLED")
                
                if status_tags:
                    has_critical = True
                    health = part.get("health", 0)
                    note = part.get("notes", "")
                    lines.append(f"   🚨 [部位警报] {part['name']}: {' '.join(status_tags)} (HP:{health}%) {note}")
            
            if not has_critical and body_status:
                 # 如果有数据但没残疾，简要显示健康度低的
                 for part in body_status:
                     if part.get("health", 100) < 50:
                         lines.append(f"   ⚠️ [部位受伤] {part['name']}: HP {part['health']}%")

            # B. Active Effects (Buff/Debuff)
            effects = char_data.get("active_effects", [])
            for ef in effects:
                dur = f"{ef['duration_chapters']}章" if ef.get('duration_chapters') > 0 else "持续"
                lines.append(f"   🌀 [状态: {ef['name']}] (Lv.{ef.get('intensity',1)}) [{dur}] - {ef.get('description', '')}")

            # C. Inventory (Structured)
            inv_list = char_data.get("inventory", [])
            if inv_list:
                items_str = []
                for item in inv_list:
                    # 兼容旧数据 (str)
                    if isinstance(item, str):
                        items_str.append(item)
                    else:
                        # Structured
                        name = item.get("name", "Unknown")
                        durability = item.get("durability", 100)
                        status = item.get("status", "Normal")
                        qty = item.get("quantity", 1)
                        
                        meta = []
                        if qty > 1: meta.append(f"x{qty}")
                        if durability <= 0: meta.append("💔已损毁")
                        elif durability < 30: meta.append("⚠️濒临损坏")
                        if status != "Normal": meta.append(f"[{status}]")
                        
                        meta_str = f" ({' '.join(meta)})" if meta else ""
                        items_str.append(f"{name}{meta_str}")
                
                lines.append(f"   🎒 物品: {', '.join(items_str)}")
            else:
                lines.append("   🎒 物品: [空]")
            
            lines.append("") # Spacer
        
        # 3. 旅行方案 (Dynamic DB Lookup)
        lines.append("## 🗺️ 可选旅行方案 (从当前位置出发)")
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
