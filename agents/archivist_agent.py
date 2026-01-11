import json
import re
from pydantic import ValidationError
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser

from core.llm import get_deepseek_chat
from core.prompts import ARCHIVIST_EXTRACT_PROMPT, ARCHIVIST_SYSTEM_PROMPT, ARCHIVIST_VALIDATION_PROMPT
from core.memory import MemoryManager
from core.schemas import ChapterExtractionSchema, RealityLayer

class ArchivistAgent:
    def __init__(self, memory_manager: MemoryManager):
        self.llm = get_deepseek_chat(temperature=0.1) 
        self.chain = ARCHIVIST_EXTRACT_PROMPT | self.llm | StrOutputParser()
        self.memory = memory_manager

    def _clean_json(self, text: str) -> str:
        """
        Robust JSON cleaning:
        1. Remove Markdown code blocks.
        2. Try to find the first '{' and last '}' to isolate the JSON object.
        3. Remove Common JSON errors like Trailing Commas (simple regex).
        """
        # 1. Strip Markdown
        text = text.replace("```json", "").replace("```", "").strip()
        
        # 2. Extract JSON block if surrounded by other text
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            text = text[start : end + 1]
            
        # 3. Handle Python 'None' -> JSON 'null' (Common LLM slip)
        text = text.replace(": None", ": null").replace(":None", ": null")
        
        # 4. Handle Trailing Commas in arrays/objects (Simple heuristic)
        # Remove comma before close bracket/brace
        text = re.sub(r',\s*}', '}', text)
        text = re.sub(r',\s*]', ']', text)
        
        return text

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
            # print(f"DEBUG RAW: {raw_response}")
        
        for attempt in range(max_retries):
            try:
                # Construct a more explicit repair prompt
                repair_messages = [
                    SystemMessage(content=ARCHIVIST_SYSTEM_PROMPT),
                    HumanMessage(content=f"【当前世界日期】：{current_date}\n\n【正文内容】\n{content}"),
                    HumanMessage(content=f"""
                    JSON 解析错误！
                    错误信息：{last_error}
                    
                    请修复你的 JSON 输出。
                    注意：
                    1. 确保所有属性名都用双引号。
                    2. 确保没有尾随逗号。
                    3. 确保字符串内的引号已转义。
                    4. 严禁使用 Markdown 代码块，只输出纯 JSON 字符串。
                    
                    请重新输出：
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

    def _validate_updates(self, extraction: ChapterExtractionSchema, chapter_num: int):
        """
        逻辑守门员：验证提取的数据是否与既定事实（历史记录）存在严重冲突。
        防止 AI 幻觉污染数据库（The Poisoned Well Problem）。
        """
        # 1. 识别涉及的实体 (Entities involved)
        entities_to_check = set()
        for char in extraction.characters:
            name = char.get("name")
            if name: entities_to_check.add(name)
        
        for rel in extraction.relationships:
            entities_to_check.add(rel.source)
            entities_to_check.add(rel.target)
            
        if not entities_to_check:
            return # 无需验证

        # 2. 批量获取既定事实 (Batch fetch established context)
        context_snippets = []
        # 我们只验证在 Graph 中已存在的实体，新实体由 Reviewer 负责合理性检查
        # 这里只做“防冲突”检查
        for entity in entities_to_check:
            ctx = self.memory.graph.query_entity_context(entity, current_chapter=chapter_num)
            # 过滤掉无效返回
            if ctx and "暂无" not in ctx and "未连接" not in ctx and "未发现" not in ctx:
                context_snippets.append(f"--- 实体: {entity} 的历史记录 ---\n{ctx}")

        if not context_snippets:
            # print("   ℹ️ 暂无相关历史记录，跳过逻辑冲突验证。")
            return 

        existing_context_str = "\n".join(context_snippets)

        # 3. 召唤逻辑法官 (Call LLM Validator)
        updates_json = extraction.model_dump_json()
        
        # 使用专门的验证 Chain
        validation_chain = ARCHIVIST_VALIDATION_PROMPT | self.llm | StrOutputParser()
        
        try:
            print("   ⚖️ 正在进行逻辑冲突验证...")
            raw_res = validation_chain.invoke({
                "existing_context": existing_context_str, 
                "proposed_updates": updates_json
            })
            clean_res = self._clean_json(raw_res)
            validation_result = json.loads(clean_res)
            
            status = validation_result.get("status")
            if status == "BLOCK":
                issues = validation_result.get("contradictions", [])
                error_lines = []
                for issue in issues:
                    entity = issue.get("entity", "Unknown")
                    desc = issue.get("issue", "No description")
                    severity = issue.get("severity", "UNKNOWN")
                    error_lines.append(f"   🛑 [{severity}] {entity}: {desc}")
                
                error_msg = "\n".join(error_lines)
                print(f"   ❌ 逻辑验证未通过！发现 {len(issues)} 个冲突。")
                print(error_msg)
                
                # 抛出异常，阻止数据库污染
                raise ValueError(f"逻辑一致性校验失败 (Consistency Violation):\n{error_msg}")
            
            elif status == "PASS":
                print("   ✅ 逻辑验证通过。")
                
            elif status == "RETCON":
                print("   🔄 触发历史修正 (RETCON) 机制...")
                instructions = validation_result.get("retcon_instructions", [])
                for instr in instructions:
                    target = instr.get("target_entity")
                    op = instr.get("operation")
                    reason = instr.get("reason")
                    
                    print(f"      🛠️ [RETCON] {op} {target}: {reason}")
                    
                    if op == "UPDATE":
                        field = instr.get("field")
                        new_val = instr.get("new_value")
                        # 尝试修补角色档案
                        # 注意：这里简化处理，直接以此名义更新 Character 表
                        # 实际上可能需要更复杂的逻辑来处理非 Character 实体
                        if field and new_val:
                            self.memory.upsert_character(target, {field: new_val}, chapter_num=chapter_num)
                            print(f"      -> 已强制更新 {target}.{field} = {new_val}")
                            
                    elif op == "MARK_FALSE":
                        # 未来实现：在 VectorDB 或 Graph 中标记某条记录为“伪史”
                        print(f"      -> (TODO) 标记关于 {target} 的相关记忆为伪史。")
                        
                print("   ✅ 历史修正完成，放行本次更新。")

            else:
                print(f"   ⚠️ 验证返回了未知状态: {status}，默认放行。")

        except (json.JSONDecodeError, ValidationError) as e:
            print(f"   ⚠️ 验证结果解析失败: {e}。为了不阻塞流程，本次暂且放行，但请留意。")
        # 注意：ValueError (Conflict) 会被上层捕获并中断流程

    def archive_chapter(self, content: str, chapter_num: int):
        print(f"🗄️ Archivist: 正在深度解析第 {chapter_num} 章...")
        
        # 1. 原文存入 VectorDB
        self.memory.add_chapter_context(content, chapter_num)
        
        try:
            focus_data = self.memory.get_narrative_focus()
            current_date = focus_data.get("date", "天道历元年1月1日")

            # 2. 提取信息
            extraction = self._extract_with_retry(content, current_date)

            # 🚨 逻辑验证 (Consistency Check)
            # 在写入数据库前，先检查是否有致命逻辑冲突
            self._validate_updates(extraction, chapter_num)
            
            # 3. 更新摘要
            self.memory.update_chapter_summary(chapter_num, extraction.summary)

            # 4. 记录事件 (带层级 Reality/Dream)
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

            # 🚨 现实锚点检查
            if len(extraction.events) > 0 and non_reality_count == len(extraction.events):
                print("   ⚠️ 检测到本章完全处于【非真实】层级，跳过角色状态和图谱更新。" )
                return 

            # 5. 更新角色
            for char_data in extraction.characters:
                name = char_data.get("name")
                if not name: continue
                
                updates = char_data.get("updates", {})
                
                # Merge top-level fields
                updates["aliases"] = char_data.get("aliases", [])
                updates["location"] = char_data.get("location")
                updates["importance"] = char_data.get("importance")
                updates["dialogue_style"] = char_data.get("dialogue_style")
                updates["dialogue_examples"] = char_data.get("dialogue_examples")
                
                # --- 处理精神账本 (Mental Ledger) ---
                mental = char_data.get("mental_update")
                if mental:
                    # 构造 MentalStateEntry
                    entry = {
                        "chapter": chapter_num,
                        "state": mental.get("state", "未知"),
                        "intensity": mental.get("intensity", 50),
                        "sanity": mental.get("sanity", 100),
                        "reason": mental.get("reason", "无")
                    }
                    updates["mental_ledger"] = [entry]
                    updates["psychological_state"] = mental.get("state")

                self.memory.upsert_character(name, updates, chapter_num)
                print(f"   👤 角色更新: {name}")

            # 6. 处理伏笔
            for hook in extraction.new_foreshadowing:
                self.memory.add_foreshadowing(chapter_num, f"[{hook.type}] {hook.content}")
                print(f"   📌 新伏笔: {hook.content[:20]}...")

            for hook_id in extraction.resolved_foreshadowing_ids:
                self.memory.resolve_foreshadowing(hook_id, chapter_num)
                print(f"   ✅ 伏笔回收: ID {hook_id}")

            # 7. 更新知识图谱
            if extraction.relationships:
                for trip in extraction.relationships:
                    # trip is a GraphTripletSchema object (Pydantic model) 
                    
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
