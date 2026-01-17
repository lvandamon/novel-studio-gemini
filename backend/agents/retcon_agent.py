import json
from typing import List, Dict, Any, Optional
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from core.llm import get_deepseek_reasoner, get_deepseek_chat
from core.memory import MemoryManager
from core.graph_store import GraphManager

# --- Prompts ---

RETCON_ANALYSIS_PROMPT = PromptTemplate.from_template("""
你是一名时空修正官 (Retcon Agent)。你的任务是分析用户的“历史修正指令”，并生成一份详细的数据库操作计划。

【当前世界状态】
{world_context}

【修正指令】
{instruction}

请分析该指令涉及的：
1. **核心实体**: 哪些角色/物品/地点的属性需要修改？
2. **关系变动**: 哪些图谱关系需要断开或新建？
3. **关键事件**: 哪些历史事件的描述需要修正？
4. **潜在风险**: 这种修改会导致哪些逻辑矛盾？（例如：如果A没死，那B继承A的遗产就不合理了）

请输出 JSON 格式的操作计划，结构如下：
{{ 
    "rationale": "修改理由分析...",
    "entity_updates": [
        {{ "name": "角色名", "field": "属性名", "new_value": "新值", "chapter_range": "all/specific" }}
    ],
    "relationship_updates": [
        {{ "source": "A", "target": "B", "relation": "OLD_REL", "action": "DELETE" }},
        {{ "source": "A", "target": "B", "relation": "NEW_REL", "action": "CREATE", "desc": "描述" }}
    ],
    "event_patches": [
        {{ "query": "相关的旧事件描述", "new_description": "修正后的事件描述", "chapter_hint": 10 }}
    ],
    "impact_warning": "警告信息..."
}}
""")

class RetconAgent:
    def __init__(self, memory_manager: MemoryManager):
        self.memory = memory_manager
        # 使用 R1 进行深度逻辑分析
        self.analyzer_llm = get_deepseek_reasoner()
        self.analysis_chain = RETCON_ANALYSIS_PROMPT | self.analyzer_llm | StrOutputParser()
        
    def _clean_json(self, text: str) -> str:
        text = text.replace("```json", "").replace("```", "").strip()
        import re
        match = re.search(r'(\{.*\})', text, re.DOTALL)
        return match.group(1) if match else text

    def analyze_retcon(self, instruction: str) -> Dict[str, Any]:
        """分析修正指令，生成计划"""
        print(f"🕵️ RetconAgent: 正在分析修正指令 -> '{instruction}'")
        
        # 1. 简单的上下文检索 (Simple Context Gathering)
        # 尝试提取指令中的实体名
        potential_entities = self.memory._extract_entities_semantically(instruction)
        context_lines = []
        for entity in potential_entities:
            # 获取角色档案
            char_data = self.memory.get_character(entity)
            if char_data:
                context_lines.append(f"角色 [{entity}]: {json.dumps(char_data, ensure_ascii=False)}")
            
            # 获取相关关系
            rels = self.memory.graph.query_entity_context(entity, recent_window=1000)
            if rels and "暂无" not in rels:
                context_lines.append(f"关系 [{entity}]:\n{rels}")
                
        world_context = "\n".join(context_lines) if context_lines else "无具体上下文。"
        
        # 2. 调用 LLM 生成计划
        response = self.analysis_chain.invoke({
            "world_context": world_context,
            "instruction": instruction
        })
        
        try:
            plan = json.loads(self._clean_json(response))
            return plan
        except Exception as e:
            return {"error": f"Plan generation failed: {e}", "raw": response}

    def execute_retcon(self, plan: Dict[str, Any], dry_run: bool = False) -> List[str]:
        """执行修正计划"""
        logs = []
        
        if dry_run:
            logs.append("--- DRY RUN MODE (No changes applied) ---")
        
        logs.append(f"🛠️ 执行修正: {plan.get('rationale', 'No rationale')}")
        
        # 1. Update Entities (SQLite)
        for update in plan.get("entity_updates", []):
            name = update["name"]
            field = update["field"]
            val = update["new_value"]
            
            action_log = f"Entity Update: {name}.{field} -> {val}"
            logs.append(action_log)
            
            if not dry_run:
                # 简单处理：更新 Character JSON
                # 注意：这里假设 field 是顶层 key，如果是嵌套的可能需要更复杂逻辑
                # memory.upsert_character 支持部分更新 merge
                # 但我们需要构造正确的结构，例如 inventory 或 attributes
                # 为了简化，Retcon 尽量只处理顶层属性或 descriptions
                update_data = {field: val}
                self.memory.upsert_character(name, update_data, chapter_num=9999) # 9999标记为修正
                
        # 2. Update Relationships (Neo4j)
        for rel in plan.get("relationship_updates", []):
            src = rel["source"]
            tgt = rel["target"]
            relation = rel["relation"]
            action = rel["action"]
            
            action_log = f"Graph {action}: {src} -[{relation}]-> {tgt}"
            logs.append(action_log)
            
            if not dry_run:
                if action == "DELETE":
                    # 逻辑删除：将 end_chapter 设为 0 或 1 (代表从一开始就不存在/或者立刻结束)
                    # 或者我们可以扩展 update_relationship 支持物理删除？
                    # GraphManager 目前只支持逻辑删除 (is_negated=True)
                    self.memory.graph.update_relationship(
                        source=src, source_type="Character", # 假设是Character
                        relation=relation,
                        target=tgt, target_type="Character",
                        is_negated=True,
                        chapter_num=0 # Retcon通常意味着“一直都是这样”，或者“从现在开始修正”
                    )
                elif action == "CREATE":
                    desc = rel.get("desc", "Retcon Created")
                    self.memory.graph.update_relationship(
                        source=src, source_type="Character",
                        relation=relation,
                        target=tgt, target_type="Character",
                        properties={"desc": desc},
                        chapter_num=0 
                    )

        # 🔥 P11: Causality Taint Analysis (Ripple Effect Check)
        impact_report = ""
        if not dry_run:
            affected_entities = set()
            for update in plan.get("entity_updates", []):
                affected_entities.add(update["name"])
            for rel in plan.get("relationship_updates", []):
                affected_entities.add(rel["source"])
            
            tainted_list = []
            impact_details = []
            
            for entity in affected_entities:
                # 1. Get downstream list
                tainted = self.memory.graph.get_downstream_dependencies(entity, depth=2)
                if tainted:
                    tainted_list.extend(tainted)
                    warning = f"⚠️ [Ripple Warning] Modifying '{entity}' may impact: {', '.join(tainted[:5])}..."
                    logs.append(warning)
                
                # 2. Get detailed impact subgraph (Text)
                subgraph_text = self.memory.graph.get_impact_subgraph(entity)
                if "系统未检测到" not in subgraph_text:
                    impact_details.append(subgraph_text)
            
            if tainted_list:
                impact_report = f"\n【潜在波及/IMPACT】\n此修正可能会影响以下实体：{', '.join(list(set(tainted_list)))}。\n"
                if impact_details:
                    impact_report += "详细影响网络：\n" + "\n".join(impact_details)

        # 3. Patch Events / VectorDB (Inject Retcon Knowledge)
        # 我们不删除旧向量，而是注入一条“高优先级”的修正规则进入 World Bible 或特殊 Retcon Collection
        for patch in plan.get("event_patches", []):
            query = patch["query"]
            new_desc = patch["new_description"]
            
            action_log = f"Memory Patch: '{query}' -> '{new_desc}'"
            logs.append(action_log)
            
            if not dry_run:
                # 将修正作为一条“绝对真理”存入 World Bible，
                # 并加上特殊的 Retcon 标签，使其检索权重极高
                # 🔥 Integrated Impact Report into the Bible Entry
                content = f"【历史修正/RETCON】关于 '{query}' 的真实情况是：{new_desc}。旧有记录若有冲突，以此为准。{impact_report}"
                self.memory.add_bible_entry(
                    category="RETCON_HISTORY",
                    topic=f"修正: {query[:10]}...",
                    content=content
                )
                
        # 4. 记录操作日志到系统事件
        if not dry_run:
            self.memory.log_event(
                chapter_num=0,
                character_name="SYSTEM",
                event_type="RETCON",
                description=f"执行了历史修正: {plan.get('rationale')}",
                layer="System"
            )
            
        return logs
