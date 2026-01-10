import json
from core.llm import get_deepseek_chat
from core.prompts import ARCHIVIST_EXTRACT_PROMPT
from core.memory import MemoryManager
from core.schemas import ChapterExtractionSchema
from langchain_core.output_parsers import StrOutputParser

class ArchivistAgent:
    def __init__(self, memory_manager: MemoryManager):
        self.llm = get_deepseek_chat(temperature=0.1) 
        self.chain = ARCHIVIST_EXTRACT_PROMPT | self.llm | StrOutputParser()
        self.memory = memory_manager

    def archive_chapter(self, content: str, chapter_num: int):
        """
        1. 提取结构化数据 (Pydantic 校验)
        2. 智能更新 SQLite 角色/物品/事件
        3. 将正文存入 ChromaDB
        """
        print(f"🗄️ Archivist: 正在深度解析第 {chapter_num} 章...")
        
        # 1. 存入 VectorDB
        self.memory.add_chapter_context(content, chapter_num)
        
        # 2. 提取并校验
        try:
            raw_response = self.chain.invoke({"content": content})
            # 清理 Markdown
            clean_json = raw_response.replace("```json", "").replace("```", "").strip()
            
            # 使用 Pydantic 强校验
            extraction = ChapterExtractionSchema.model_validate_json(clean_json)
            
            # 3. 更新摘要
            self.memory.update_chapter_summary(chapter_num, extraction.summary)

            # 4. 更新角色 (使用 MemoryManager 的智能合并)
            for char_data in extraction.characters:
                name = char_data.get("name")
                if name:
                    # 将 updates 展平到 char_data 中以便 upsert
                    updates = char_data.get("updates", {})
                    char_data.update(updates)
                    self.memory.upsert_character(name, char_data, chapter_num)
                    print(f"   👤 角色更新: {name}")

            # 5. 记录事件
            for event in extraction.events:
                self.memory.log_event(
                    chapter_num, 
                    event.character, 
                    event.type, 
                    f"{event.description} (影响: {event.impact})"
                )
                print(f"   🎭 事件记录: {event.character} -> {event.type}")

            # 6. 处理伏笔
            for hook in extraction.new_foreshadowing:
                self.memory.add_foreshadowing(chapter_num, f"[{hook.type}] {hook.content}")
                print(f"   📌 新伏笔: {hook.content[:20]}...")

            for hook_id in extraction.resolved_foreshadowing_ids:
                self.memory.resolve_foreshadowing(hook_id, chapter_num)
                print(f"   ✅ 伏笔回收: ID {hook_id}")

        except Exception as e:
            print(f"   ❌ Archivist 报错: {e}")
            # 这里可以考虑加入重试逻辑或保存原始输出供调试
