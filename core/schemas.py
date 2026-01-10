from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class CharacterSchema(BaseModel):
    name: str
    role: str = "未知"
    level: str = "未知"
    personality: List[str] = Field(default_factory=list)
    relationships: Dict[str, str] = Field(default_factory=dict)
    inventory: List[str] = Field(default_factory=list)
    goals: List[str] = Field(default_factory=list)
    current_state: str = "正常"
    last_updated_chapter: int = 0

class EventSchema(BaseModel):
    character: str
    type: str # e.g., "status_change", "acquisition", "conflict", "secret"
    description: str
    impact: str = "中等" # 影响评估：轻微, 中等, 重大

class ForeshadowingSchema(BaseModel):
    content: str
    type: str = "plot_hook"
    importance: int = 3 # 1-5 
    potential_resolution: Optional[str] = None

class ChapterExtractionSchema(BaseModel):
    """Archivist 从章节中提取的所有结构化信息"""
    summary: str
    characters: List[Dict[str, Any]] # 这里暂时用 dict，后续在 logic 里与 CharacterSchema 合并
    events: List[EventSchema]
    new_foreshadowing: List[ForeshadowingSchema]
    resolved_foreshadowing_ids: List[int] = Field(default_factory=list)
    world_updates: List[str] = Field(default_factory=list)
