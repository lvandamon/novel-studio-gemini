import json
from typing import List, Dict, Any
from langchain_core.output_parsers import StrOutputParser
from core.llm import get_deepseek_reasoner
from core.prompts import CAUSALITY_SIMULATION_PROMPT
from core.memory import MemoryManager

class CausalitySimulator:
    """
    🔥 P10: 因果模拟器 (The Oracle)
    """
    def __init__(self, memory_manager: MemoryManager):
        self.memory = memory_manager
        self.graph = memory_manager.graph
        self.llm = get_deepseek_reasoner()
        self.chain = CAUSALITY_SIMULATION_PROMPT | self.llm | StrOutputParser()

    def simulate_action(self, action_description: str, target_entities: List[str]) -> Dict[str, Any]:
        """模拟动作后果"""
        print(f"🔮 Causality: 推演 -> [{action_description}]")
        
        # 1. Impact Subgraph
        subgraphs = []
        for entity in target_entities:
            sg = self.graph.get_impact_subgraph(entity)
            if "未检测到" not in sg: subgraphs.append(sg)
        full_graph = "\n".join(subgraphs) if subgraphs else "（无复杂关系）"

        # 2. Hooks
        hooks = self.memory.get_active_foreshadowing()
        imp_hooks = [f"[ID:{h['id']}] {h['content']}" for h in hooks if h.get('importance', 5) >= 5]
        hooks_ctx = "\n".join(imp_hooks)

        # 3. Plan
        plan = self.memory.get_active_plan()
        future_plan = f"Vol: {plan.get('volume', {}).get('goal')}\nArc: {plan.get('arc', {}).get('goal')}"

        try:
            response = self.chain.invoke({
                "action": action_description,
                "impact_graph": full_graph,
                "active_hooks": hooks_ctx,
                "future_plan": future_plan
            })
            
            # Clean
            clean = response.strip()
            if "```" in clean:
                 import re
                 match = re.search(r'(\{.*\})', clean, re.DOTALL)
                 if match: clean = match.group(1)
            
            result = json.loads(clean)
            if result.get("risk_level") in ["HIGH", "CRITICAL"]:
                print(f"   🚨 高危因果: {result.get('verdict')}")
            return result
        except Exception as e:
            print(f"   ⚠️ Sim Failed: {e}")
            return {"risk_level": "UNKNOWN", "verdict": "SAFE"}