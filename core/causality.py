import json
from typing import List, Dict, Any, Optional
from langchain_core.output_parsers import StrOutputParser
from core.llm import get_deepseek_reasoner
from core.prompts import CAUSALITY_SIMULATION_PROMPT
from core.graph_store import GraphManager
from core.memory import MemoryManager

class CausalitySimulator:
    """
    🔥 P10新增: 因果模拟器 (The Oracle)
    负责在剧情发生前，预测其对世界观、人际关系和未来规划的连锁影响。
    """
    def __init__(self, memory_manager: MemoryManager):
        self.memory = memory_manager
        self.graph = memory_manager.graph
        # 使用 R1 (Reasoner) 模型进行深度推演
        self.llm = get_deepseek_reasoner()
        self.chain = CAUSALITY_SIMULATION_PROMPT | self.llm | StrOutputParser()

    def _clean_json(self, text: str) -> str:
        text = text.replace("```json", "").replace("```", "").strip()
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            text = text[start : end + 1]
        return text

    def simulate_action(self, action_description: str, target_entities: List[str]) -> Dict[str, Any]:
        """
        模拟某个动作的后果。
        
        Args:
            action_description: 动作描述 (e.g. "萧风在决斗中杀死了赵虎")
            target_entities: 受影响的主要实体名列表 (e.g. ["赵虎"])
            
        Returns:
            Risk Assessment JSON
        """
        print(f"🔮 Causality: 正在推演动作后果 -> [{action_description}]")
        
        # 1. 获取影响子图 (Impact Subgraph)
        subgraphs = []
        for entity in target_entities:
            sg = self.graph.get_impact_subgraph(entity)
            if "未检测到" not in sg:
                subgraphs.append(sg)
        
        full_graph_context = "\n".join(subgraphs) if subgraphs else "（目标似乎是孤立节点，无复杂社会关系）"

        # 2. 获取活跃伏笔 (只取高优先级的)
        hooks = self.memory.get_active_foreshadowing()
        # 过滤出 Importance >= 5 的
        important_hooks = [f"[ID:{h['id']}] {h['content']}" for h in hooks if h.get('importance', 5) >= 5]
        hooks_context = "\n".join(important_hooks) if important_hooks else "无重要活跃伏笔"

        # 3. 获取未来规划
        plan = self.memory.get_active_plan()
        future_plan = f"Volume: {plan.get('volume', {}).get('goal')}\nArc: {plan.get('arc', {}).get('goal')}"

        # 4. LLM 推演
        try:
            response = self.chain.invoke({
                "action": action_description,
                "impact_graph": full_graph_context,
                "active_hooks": hooks_context,
                "future_plan": future_plan
            })
            
            clean_res = self._clean_json(response)
            result = json.loads(clean_res)
            
            # 打印高风险警告
            if result.get("risk_level") in ["HIGH", "CRITICAL"]:
                print(f"   🚨 因果高危预警: {result.get('verdict')}")
                print(f"      破坏规划: {result.get('plan_disruption')}")
                for c in result.get("consequences", []):
                    print(f"      -> {c['description']}")
            else:
                print(f"   ✅ 因果推演安全 (Risk: {result.get('risk_level')})")
                
            return result

        except Exception as e:
            print(f"   ⚠️ 因果推演失败: {e}")
            return {
                "risk_level": "UNKNOWN", 
                "verdict": "SAFE", 
                "reason": f"Simulation failed: {e}"
            }
