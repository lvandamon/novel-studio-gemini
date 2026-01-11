import json
from pydantic import ValidationError
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser

from core.llm import get_deepseek_chat
from core.prompts import ARCHIVIST_EXTRACT_PROMPT, ARCHIVIST_SYSTEM_PROMPT
from core.memory import MemoryManager
from core.schemas import ChapterExtractionSchema, RealityLayer

class ArchivistAgent:
    def __init__(self, memory_manager: MemoryManager):
        self.llm = get_deepseek_chat(temperature=0.1) 
        self.chain = ARCHIVIST_EXTRACT_PROMPT | self.llm | StrOutputParser()
        self.memory = memory_manager

    def _clean_json(self, text: str) -> str:
        return text.replace("```json", "").replace("```", "").strip()

    def _extract_with_retry(self, content: str, current_date: str, max_retries: int = 3) -> ChapterExtractionSchema:
        raw_response = ""
        last_error = ""

        try:
            raw_response = self.chain.invoke({"content": content, "current_date": current_date})
            clean_json = self._clean_json(raw_response)
            return ChapterExtractionSchema.model_validate_json(clean_json)
        except (ValidationError, json.JSONDecodeError) as e:
            print(f"   ⚠️ Archivist: 第一次提取失败 ({type(e).__name__})。正在尝试自动修复...")
            last_error = str(e)
        
        for attempt in range(max_retries):
            try:
                repair_messages = [
                    SystemMessage(content=ARCHIVIST_SYSTEM_PROMPT),
                    HumanMessage(content=f"【当前世界日期】：{current_date}\n\n【正文内容】\n{content}"),
                    HumanMessage(content=f"""
                    上一次生成的 JSON 解析失败或校验未通过。
                    错误信息：{last_error}
                    上次错误片段：{raw_response[:500]}...                    请重新分析正文，并严格按照 JSON 格式要求输出修复后的结果。
                    """)
                ]
                response_msg = self.llm.invoke(repair_messages)
                raw_response = response_msg.content
                clean_json = self._clean_json(raw_response)
                return ChapterExtractionSchema.model_validate_json(clean_json)
            except (ValidationError, json.JSONDecodeError) as e:
                print(f"   ⚠️ 重试第 {attempt + 1}/{max_retries} 次失败: {e}")
                last_error = str(e)
        
        raise ValueError(f"Archivist 严重错误：经过 {max_retries} 次重试后仍无法提取有效数据。\n最后错误: {last_error}")

    def archive_chapter(self, content: str, chapter_num: int):
        print(f"🗄️ Archivist: 正在深度解析第 {chapter_num} 章...")
        
        # 1. 原文存入 VectorDB
        self.memory.add_chapter_context(content, chapter_num)
        
        try:
            focus_data = self.memory.get_narrative_focus()
            current_date = focus_data.get("date", "天道历元年1月1日")

            # 2. 提取信息
            extraction = self._extract_with_retry(content, current_date)
            
            # 3. 更新摘要
            self.memory.update_chapter_summary(chapter_num, extraction.summary)

            # 4. 记录事件 (带层级 Reality/Dream)
            # 我们检查这一章的主要层级。如果大部分事件是 Dream，我们就不应该更新世界状态。
            # 这里做一个简单的启发式判断：如果 extraction 里明确标记了非 Reality 的事件，我们记录下来。
            
            non_reality_count = 0
            for event in extraction.events:
                self.memory.log_event(
                    chapter_num, 
                    event.character, 
                    event.type, 
                    f"{event.description} (影响: {event.impact})",
                    layer=event.layer.value
                )
                if event.layer != RealityLayer.REALITY:
                    non_reality_count += 1
                print(f"   🎭 事件记录 [{event.layer.value}]: {event.character} -> {event.type}")

            # 🚨 现实锚点检查：如果本章全是幻境，跳过状态更新
            if len(extraction.events) > 0 and non_reality_count == len(extraction.events):
                print("   ⚠️ 检测到本章完全处于【非真实】层级，跳过角色状态和图谱更新。" )
                return 

            # 5. 更新角色 (仅当层级允许)
            for char_data in extraction.characters:
                name = char_data.get("name")
                if name:
                    updates = char_data.get("updates", {}) # 兼容旧 prompt 格式
                    if not updates: 
                        # 如果没有 updates 字段，假设 char_data 本身就是更新数据
                        # 排除 name, id 等字段
                        updates = {k:v for k,v in char_data.items() if k not in ['name', 'id']}
                    
                    if updates:
                        self.memory.upsert_character(name, updates, chapter_num)
                        print(f"   👤 角色更新: {name}")

            # 6. 处理伏笔
            for hook in extraction.new_foreshadowing:
                self.memory.add_foreshadowing(chapter_num, f"[{hook.type}] {hook.content}")
                print(f"   📌 新伏笔: {hook.content[:20]}...")

            for hook_id in extraction.resolved_foreshadowing_ids:
                self.memory.resolve_foreshadowing(hook_id, chapter_num)
                print(f"   ✅ 伏笔回收: ID {hook_id}")

            # 7. 更新知识图谱 (支持删除)
            if extraction.relationships:
                for trip in extraction.relationships:
                    self.memory.graph.update_relationship(
                        source=trip.source,
                        source_type=trip.source_type,
                        relation=trip.relation,
                        target=trip.target,
                        target_type=trip.target_type,
                        properties={"desc": trip.desc},
                        is_negated=trip.is_negated,
                        chapter_num=chapter_num
                    )
                    action = "❌删除" if trip.is_negated else "🔗连接"
                    print(f"   🕸️ 图谱{action}: {trip.source} --{trip.relation}--> {trip.target}")
            
            # 8. 更新世界日期
            if extraction.current_date:
                self.memory.update_world_date(extraction.current_date)
                print(f"   📅 日期更新: {extraction.current_date}")

        except Exception as e:
            print(f"   ❌ FATAL: 第 {chapter_num} 章归档失败！\n原因: {e}")
            raise e