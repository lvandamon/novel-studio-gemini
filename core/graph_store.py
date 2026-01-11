import os
from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase

class GraphManager:
    def __init__(self, uri: str = None, user: str = None, password: str = None):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "password")
        self.driver = None
        self._connect()

    def _connect(self):
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            self.driver.verify_connectivity()
            # print("✅ Neo4j 连接成功") 
        except Exception as e:
            # print(f"⚠️ Neo4j 连接失败: {e}. 图谱功能将不可用。")
            self.driver = None

    def close(self):
        if self.driver:
            self.driver.close()

    def is_connected(self) -> bool:
        return self.driver is not None
        
    def _sanitize_label(self, label: str) -> str:
        """Sanitize label to be safe for Cypher by wrapping in backticks"""
        # Remove any existing backticks to avoid injection
        clean = label.replace("`", "")
        return f"`{clean}`"

    def update_relationship(self, source: str, source_type: str, relation: str, target: str, target_type: str, properties: Dict = None, is_negated: bool = False, chapter_num: int = 0):
        """
        全能关系管理：支持建立新关系、更新属性、以及逻辑删除关系。
        """
        if not self.driver: return
        
        # Sanitize Labels
        source_label = self._sanitize_label(source_type)
        target_label = self._sanitize_label(target_type)
        relation_type = self._sanitize_label(relation.upper()).replace("`", "") # Relation types usually don't need backticks if simple, but better safe. Actually, relationship types in Cypher usually stick to simple chars. But wrapping in backticks is valid for types too.
        # Let's use backticks for relation type too.
        relation_label = f"`{relation.upper().replace('`', '')}`"


        if is_negated:
            self._logical_delete_relationship(source, relation_label, target, chapter_num)
        else:
            self._upsert_relationship(source, source_label, relation_label, target, target_label, properties, chapter_num)

    def _logical_delete_relationship(self, source: str, relation_label: str, target: str, chapter_num: int):
        """逻辑删除：设置 end_chapter"""
        query = f"""
        MATCH (a {{name: $source}})-[r:{relation_label}]->(b {{name: $target}})
        WHERE r.end_chapter IS NULL
        SET r.end_chapter = $chapter_num, r.updated_at = timestamp()
        """
        with self.driver.session() as session:
            session.run(query, source=source, target=target, chapter_num=chapter_num)

    def _upsert_relationship(self, source: str, source_label: str, relation_label: str, target: str, target_label: str, properties: Dict = None, chapter_num: int = 0):
        """插入或更新关系，包含 start_chapter"""
        # Note: source_label, target_label, relation_label MUST be pre-sanitized and include backticks if needed
        
        query = f"""
        MERGE (a:{source_label} {{name: $source_name}})
        MERGE (b:{target_label} {{name: $target_name}})
        WITH a, b
        MATCH (a)-[r:{relation_label}]->(b)
        WHERE r.end_chapter IS NULL
        SET r.updated_at = timestamp()
        """
        
        fallback_query = f"""
        MERGE (a:{source_label} {{name: $source_name}})
        MERGE (b:{target_label} {{name: $target_name}})
        MERGE (a)-[r:{relation_label}]->(b)
        ON CREATE SET r.start_chapter = $chapter_num, r.updated_at = timestamp()
        """
        
        params = {
            "source_name": source,
            "target_name": target,
            "chapter_num": chapter_num,
            ** (properties or {})
        }

        if properties:
            prop_set_clause = ", ".join([f"r.{k} = ${k}" for k in properties.keys()])
            query += f", {prop_set_clause}"
            fallback_query += f", {prop_set_clause}"

        with self.driver.session() as session:
            result = session.run(query, params)
            if result.consume().counters.properties_set == 0:
                session.run(fallback_query, params)

    def query_entity_context(self, entity_name: str, current_chapter: int = 999999) -> str:
        """查询在特定章节有效的实体上下文"""
        if not self.driver: return "（图谱未连接）"

        query = f"""
        MATCH (a {{name: $name}})-[r]-(b)
        WHERE (r.start_chapter IS NULL OR r.start_chapter <= $current_chapter)
          AND (r.end_chapter IS NULL OR r.end_chapter > $current_chapter)
        RETURN type(r) as rel, b.name as target, labels(b) as target_type, startNode(r) = a as is_outgoing, r.desc as desc
        LIMIT 50
        """
        
        context_lines = []
        with self.driver.session() as session:
            result = session.run(query, name=entity_name, current_chapter=current_chapter)
            for record in result:
                rel_type = record["rel"]
                target = record["target"]
                desc = f" ({record['desc']})" if record["desc"] else ""
                
                if record["is_outgoing"]:
                    line = f"({entity_name}) --[{rel_type}]--> ({target}){desc}"
                else:
                    line = f"({target}) --[{rel_type}]--> ({entity_name}){desc}"
                context_lines.append(line)

        if not context_lines:
            return f"图谱中暂无关于 {entity_name} 的有效关系记录（截至第 {current_chapter} 章）。"
            
        return "\n".join(context_lines)

    def find_path_between(self, start: str, end: str, max_depth: int = 3) -> str:
        if not self.driver: return ""

        query = f"""
        MATCH p = shortestPath((a {{name: $start}})-[*..{max_depth}]-(b {{name: $end}}))
        RETURN p
        """
        
        with self.driver.session() as session:
            result = session.run(query, start=start, end=end)
            record = result.single()
            if record:
                path = record["p"]
                nodes = [n["name"] for n in path.nodes]
                rels = [r.type for r in path.relationships]
                
                path_str = ""
                for i in range(len(rels)):
                    path_str += f"({nodes[i]}) -[{rels[i]}]- "
                path_str += f"({nodes[-1]})"
                return path_str
            
        return "未发现直接联系。"

    def get_visualization_data(self, limit: int = 100) -> Dict[str, List[Dict]]:
        if not self.driver:
            return {"nodes": [], "edges": []}
            
        query = f"""
        MATCH (n)-[r]->(m)
        RETURN n.name as source, labels(n) as source_label, 
               type(r) as relation, 
               m.name as target, labels(m) as target_label
        LIMIT $limit
        """
        
        nodes = {}
        edges = []
        
        color_map = {
            "Character": "#97c2fc", 
            "Organization": "#fb7e81", 
            "Location": "#7be141", 
            "Item": "#ffbf00", 
            "Event": "#eb7df4"
        }

        with self.driver.session() as session:
            result = session.run(query, limit=limit)
            for record in result:
                s_name = record["source"]
                s_label = record["source_label"][0] if record["source_label"] else "Unknown"
                t_name = record["target"]
                t_label = record["target_label"][0] if record["target_label"] else "Unknown"
                rel = record["relation"]
                
                if s_name not in nodes:
                    nodes[s_name] = {"id": s_name, "label": s_name, "group": s_label, "color": color_map.get(s_label, "#cccccc")}
                if t_name not in nodes:
                    nodes[t_name] = {"id": t_name, "label": t_name, "group": t_label, "color": color_map.get(t_label, "#cccccc")}
                
                edges.append({"from": s_name, "to": t_name, "label": rel, "arrows": "to"})
                
        return {"nodes": list(nodes.values()), "edges": edges}