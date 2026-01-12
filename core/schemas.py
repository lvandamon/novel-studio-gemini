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

class MentalStateEntry(BaseModel):
    chapter: int
    state: str # e.g. "绝望", "狂喜"
    intensity: int = Field(..., ge=0, le=100) # 情绪烈度 (0-100)
    sanity: int = Field(100, ge=0, le=100) # 理智值/SAN值 (0-100)
    reason: str

class CharacterSchema(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    aliases: List[str] = Field(default_factory=list) # e.g. ["厉飞雨", "韩跑跑"]
    role: str = "未知"
    level: str = "未知"
    personality: List[str] = Field(default_factory=list) # 静态性格标签
    psychological_state: str = "平稳" # 简要当前状态
    mental_ledger: List[MentalStateEntry] = Field(default_factory=list) # 精神体检账本 (Mental State Ledger)
    relationships: Dict[str, str] = Field(default_factory=dict)
    inventory: List[str] = Field(default_factory=list)
    gold: int = Field(default=0, description="角色持有的金币数量")
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

class AtmosphereSchema(BaseModel):
    tone: str # 基调 (e.g. 压抑, 欢快)
    tension: float = Field(..., ge=0.0, le=1.0) # 紧张度 (0.0 - 1.0)
    mystery: float = Field(..., ge=0.0, le=1.0) # 悬疑度
    romance: float = Field(..., ge=0.0, le=1.0) # 情感/浪漫度
    sensory_focus: str # 视觉/听觉/嗅觉
    color_palette: str # 场景色调 (e.g. 灰白, 血红)

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