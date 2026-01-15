from core.memory import MemoryManager
from core.schemas import ArcStatus

def init_plan(memory_manager=None):
    memory = memory_manager if memory_manager else MemoryManager()
    
    print("Checking existing plan...")
    # 1. Check if plan exists
    active = memory.get_active_plan()
    if active["volume"] or active["arc"]:
        print("✅ Active plan found:")
        if active["volume"]:
            print(f"  Volume: {active['volume']['name']} - {active['volume']['goal']}")
        if active["arc"]:
            print(f"  Arc: {active['arc']['name']} - {active['arc']['goal']}")
            print(f"  Next Steps: {active['arc']['key_events']}")
        return

    print("Initializing Volume 1...")
    
    # 2. Create Volume 1
    vol_id = memory.create_volume(
        name="第一卷 云州往事",
        description="主角萧风在云州修仙界的崛起之路，从外门弟子到筑基修士。",
        goal="筑基成功，查清身世线索，离开云州。"
    )
    
    # 3. Create Arc 1
    arc_id = memory.create_arc(
        volume_id=vol_id,
        name="青云惊变",
        description="萧风获得神秘戒指，在宗门大比中崭露头角，却卷入宗门覆灭的危机。",
        goal="获得筑基丹，在宗门覆灭中幸存。",
        key_events=[
            "获得神秘戒指 (已完成)", 
            "外门大比夺魁 (进行中)",
            "发现掌门秘密 (待触发)",
            "魔道入侵青云门 (高潮)",
            "逃离宗门 (结局)"
        ],
        start_chapter=1
    )
    
    # 4. Activate
    memory.activate_arc(arc_id, start_chapter=1)
    
    print("🎉 Plan initialized successfully!")
    print(memory.get_active_plan())

if __name__ == "__main__":
    init_plan()
