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

class CharacterSchema(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    aliases: List[str] = Field(default_factory=list) # e.g. ["厉飞雨", "韩跑跑"]
    role: str = "未知"
    level: str = "未知"
    personality: List[str] = Field(default_factory=list)
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