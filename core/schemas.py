from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum
import uuid

class RealityLayer(str, Enum):
    REALITY = "Reality"
    DREAM = "Dream"
    HALLUCINATION = "Hallucination"
    HISTORY = "History"
    SIMULATION = "Simulation"

class ArcStatus(str, Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"

class ArcSchema(BaseModel):
    id: Optional[int] = None
    volume_id: Optional[int] = None
    name: str
    description: str
    goal: str
    key_events: List[str] = Field(default_factory=list) # 本单元必须发生的关键事件点
    start_chapter: Optional[int] = None
    end_chapter_estimated: Optional[int] = None
    status: ArcStatus = ArcStatus.PLANNED

class VolumeSchema(BaseModel):
    id: Optional[int] = None
    name: str
    description: str
    goal: str
    status: ArcStatus = ArcStatus.PLANNED

class CharacterSchema(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    aliases: List[str] = Field(default_factory=list) # e.g. ["厉飞雨", "韩跑跑"]
    role: str = "未知"
    level: str = "未知"
    personality: List[str] = Field(default_factory=list) # 静态性格标签
    psychological_state: str = "平稳" # 动态心理状态，e.g. "焦虑", "杀意沸腾", "心如死灰"
    psychological_history: List[Dict[str, Any]] = Field(default_factory=list) # e.g. [{"chapter": 10, "state": "绝望", "reason": "家族被灭"}]
    relationships: Dict[str, str] = Field(default_factory=dict)
    inventory: List[str] = Field(default_factory=list)
    goals: List[str] = Field(default_factory=list)
    current_state: str = "正常"
    location: str = "未知" 
    importance: str = "NPC" # 可选: "Protagonist", "Major", "Minor", "NPC"
    last_updated_chapter: int = 0
    dialogue_style: str = ""
    dialogue_examples: List[str] = Field(default_factory=list)

class EventSchema(BaseModel):
    character: str
    type: str 
    description: str
    impact: str = "中等"
    layer: RealityLayer = RealityLayer.REALITY # 默认是真实发生的

class ForeshadowingSchema(BaseModel):
    content: str
    type: str = "plot_hook"
    importance: int = 3 
    potential_resolution: Optional[str] = None

class GraphTripletSchema(BaseModel):
    source: str
    source_type: str = "Character"
    relation: str
    target: str
    target_type: str = "Character"
    desc: str = ""
    is_negated: bool = False # 如果为 True，表示删除该关系

class ChapterExtractionSchema(BaseModel):
    summary: str
    characters: List[Dict[str, Any]] 
    events: List[EventSchema]
    relationships: List[GraphTripletSchema] = Field(default_factory=list)
    new_foreshadowing: List[ForeshadowingSchema]
    resolved_foreshadowing_ids: List[int] = Field(default_factory=list)
    world_updates: List[Dict[str, Any]] = Field(default_factory=list)
    current_date: str = Field(..., description="更新后的世界日期")