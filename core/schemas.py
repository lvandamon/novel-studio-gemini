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

class AnchorStatus(str, Enum):
    ACTIVE = "active"           # 当前生效
    ARCHIVED = "archived"       # 历史版本 (已过时)
    SHATTERED = "shattered"     # 被剧情击碎 (如: "不杀"原则被打破)
    TRANSCENDED = "transcended" # 升华/融合 (如: "复仇"升级为"大义")

class CharacterEpochSchema(BaseModel):
    name: str  # e.g. "青涩少年期", "宗门复仇期"
    description: str # 这一时期的主要性格特征描述
    start_chapter: int
    trigger_event: str # 导致进入这一时期的关键事件

class CharacterEvolutionSchema(BaseModel):
    """用于 Archivist 提取角色性格质变事件"""
    character_name: str
    new_epoch_name: str
    trigger_reason: str
    shattered_anchors: List[str] = Field(default_factory=list) # 被打破的旧锚点内容
    new_anchors: List[Dict[str, str]] = Field(default_factory=list) # {"category": "...", "content": "..."}

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

# --- Hard Logic Extensions (v2.0) ---

class BodyPartStatus(BaseModel):
    name: str # e.g. "左臂", "丹田", "神识"
    health: int = Field(100, ge=0, le=100)
    is_severed: bool = False # 是否缺失/断裂 (永久性物理损伤)
    is_crippled: bool = False # 是否残废 (功能性丧失)
    notes: str = "" # e.g. "被魔气侵蚀，无法运气"

class StatusEffect(BaseModel):
    name: str # e.g. "剧毒", "走火入魔", "剑意护体"
    description: str
    intensity: int = 1 # 层数/烈度
    duration_chapters: int = 0 # 剩余持续章节数 (0表示永久或直到治愈)
    is_hidden: bool = False # 是否对本人隐藏 (如潜伏期病毒)

class InventoryItem(BaseModel):
    name: str
    category: str = "General" # Weapon, Consumable, KeyItem
    description: str = ""
    quantity: int = 1
    durability: int = 100 # 100=Perfect, 0=Broken
    status: str = "Normal" # "Normal", "Cursed", "Sealed"
    is_equipped: bool = False

class CharacterSchema(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    aliases: List[str] = Field(default_factory=list) # e.g. ["厉飞雨", "韩跑跑"]
    role: str = "未知"
    level: str = "未知"
    personality: List[str] = Field(default_factory=list) # 静态性格标签
    
    # --- State & Physiology ---
    psychological_state: str = "平稳" # 简要心理状态
    current_state: str = "正常" # 简要生理状态 (Legacy summary)
    
    # [New] Hard Logic Fields
    body_status: List[BodyPartStatus] = Field(default_factory=list) # 身体部件状态 (为空则默认健康)
    active_effects: List[StatusEffect] = Field(default_factory=list) # 当前生效的 Buff/Debuff
    
    mental_ledger: List[MentalStateEntry] = Field(default_factory=list) # 精神体检账本
    relationships: Dict[str, str] = Field(default_factory=dict)
    
    # [New] Structured Inventory
    inventory: List[InventoryItem] = Field(default_factory=list) # 结构化物品栏
    # Legacy field support (for backward compatibility during migration)
    # inventory_str: List[str] = Field(default_factory=list) 
    
    gold: int = Field(default=0, description="角色持有的金币数量")
    goals: List[str] = Field(default_factory=list)
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
    character_evolutions: List[CharacterEvolutionSchema] = Field(default_factory=list) # 🔥 P9新增: 角色性格演化事件
    world_updates: List[Dict[str, Any]] = Field(default_factory=list)
    current_date: str = Field(..., description="更新后的世界日期")