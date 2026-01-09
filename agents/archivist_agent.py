import json
from core.llm import get_deepseek_chat
from core.prompts import ARCHIVIST_EXTRACT_PROMPT
from core.memory import MemoryManager
from langchain_core.output_parsers import StrOutputParser

class ArchivistAgent:
    def __init__(self, memory_manager: MemoryManager):
        self.llm = get_deepseek_chat(temperature=0.1) # 提取信息需要低温精确
        self.chain = ARCHIVIST_EXTRACT_PROMPT | self.llm | StrOutputParser()
        self.memory = memory_manager

    def archive_chapter(self, content: str, chapter_num: int):
        """
        1. 提取结构化数据更新 SQLite
        2. 将正文存入 ChromaDB
        """
        print(f"🗄️ 档案员 (Archivist) 正在整理第 {chapter_num} 章的数据...")
        
        # 1. 存入 VectorDB
        self.memory.add_chapter_context(content, chapter_num)
        
        # 2. 提取并更新 SQLite
        try:
            json_str = self.chain.invoke({"content": content})
            # 清理可能的 markdown 标记
            json_str = json_str.replace("```json", "").replace("```", "").strip()
            
            data = json.loads(json_str)
            
            # 更新角色
            if "characters" in data:
                for char_update in data["characters"]:
                    name = char_update.get("name")
                    if not name: continue
                    
                    # 获取旧数据并合并 (这里简化为直接更新/覆盖字段)
                    existing_data = self.memory.get_character(name) or {}
                    updates = char_update.get("updates", {})
                    # 简单的字典合并
                    existing_data.update(updates)
                    # 确保有一个基础结构
                    if "name" not in existing_data: existing_data["name"] = name
                    
                    self.memory.upsert_character(name, existing_data)
                    print(f"   -> 更新角色档案: {name}")

            # 更新物品 (逻辑类似)
            if "items" in data:
                # 暂时略过物品的详细实现，逻辑同上
                pass
                
        except json.JSONDecodeError:
            print("   ⚠️ 警告: 档案员提取的 JSON 格式错误，本次跳过结构化更新。")
        except Exception as e:
            print(f"   ⚠️ 警告: 档案整理出错: {e}")
