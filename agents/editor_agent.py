import json
import re
from typing import Dict, Any
from langchain_core.output_parsers import StrOutputParser
from core.llm import get_deepseek_reasoner
from core.prompts import EDITOR_GEN_OUTLINE_PROMPT
from core.context_manager import ContextManager
from core.schemas import AtmosphereSchema

class EditorAgent:
    def __init__(self, context_manager: ContextManager):
        # Editor use Reasoner (R1) for logical plot planning
        self.llm = get_deepseek_reasoner() 
        self.chain = EDITOR_GEN_OUTLINE_PROMPT | self.llm | StrOutputParser()
        self.context_manager = context_manager
        self.memory = context_manager.memory

    def _get_causal_context(self, active_characters: list) -> str:
        """从图谱中提取关键角色的因果链背景"""
        if not self.memory.graph.is_connected() or not active_characters:
            return ""
        
        causal_report = ["### 🕸️ 因果链追溯 (Causal Context)"]
        for char in active_characters:
            # 1. 查询角色的社交/状态关系
            rel_context = self.memory.graph.query_entity_context(char)
            if "暂无" not in rel_context:
                causal_report.append(f"【{char} 的既定关系】:\n{rel_context}")
            
            # 2. 尝试寻找因果链 (这里可以根据需要扩展，比如查找最近参与的重大事件)
            # 暂时使用 entity_context 提供的关系作为基础，
            # 也可以在这里增加特定的因果追溯逻辑。
        
        return "\n".join(causal_report) if len(causal_report) > 1 else ""

    def _clean_json(self, text: str) -> str:
        """
        针对 Reasoner 模型的鲁棒 JSON 提取器
        1. 移除 <think> 思考过程
        2. 提取 markdown json 块
        3. 兜底提取 {}
        """
        # 1. 移除 <think> 标签及其内容 (非贪婪匹配)
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        
        # 2. 尝试匹配 ```json ... ```
        match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            return match.group(1)
            
        # 3. 尝试匹配最外层的 {}
        match = re.search(r'(\{.*\})', text, re.DOTALL)
        if match:
            return match.group(1)
            
        return text.strip()

    def generate_outline(self, chapter_num: int, context_package: str, causal_context: str = "") -> Dict[str, Any]:
        """
        调用 R1 模型生成章节大纲，并进行格式清洗和补全。
        """
        print(f"🧠 Editor: 正在构思第 {chapter_num} 章大纲 (DeepSeek-R1)...")
        
        full_context = context_package
        if causal_context:
            full_context += f"\n\n{causal_context}"

        try:
            raw_output = self.chain.invoke({
                "context": full_context,
                "chapter_num": chapter_num
            })
            
            cleaned_json = self._clean_json(raw_output)
            data = json.loads(cleaned_json)
            
            # --- 字段完整性校验与补全 ---
            
            # 1. Title
            if "title" not in data:
                data["title"] = f"第 {chapter_num} 章"

            # 1.5 Estimated Duration (New)
            if "estimated_duration" not in data:
                data["estimated_duration"] = "未知"
                
            # 2. Outline (标准化为 List[str])
            if "outline" not in data:
                data["outline"] = ["本章大纲生成失败，请人工核查。"]
            elif isinstance(data["outline"], str):
                # 如果模型偷懒只返回了字符串，尝试按行分割
                data["outline"] = [line.strip() for line in data["outline"].split('\n') if line.strip()]
                
            # 3. Active Characters
            if "active_characters" not in data:
                data["active_characters"] = []
                
            # 4. Scene Location
            if "scene_location" not in data:
                data["scene_location"] = "未知地点"
                
            # 5. Atmosphere (确保是 Dict)
            if "atmosphere" not in data or not isinstance(data["atmosphere"], dict):
                data["atmosphere"] = {
                    "tone": "正常",
                    "sensory_focus": "视觉",
                    "color_palette": "正常"
                }

            print(f"   ✅ 大纲生成完毕: 《{data['title']}》- 共 {len(data['outline'])} 个节点")
            return data

        except json.JSONDecodeError:
            print(f"   ⚠️ Editor JSON 解析失败。Raw output:\n{raw_output[:200]}...")
            return {
                "title": f"第 {chapter_num} 章 (解析错误)",
                "outline": ["大纲生成数据格式错误，请检查日志。"],
                "active_characters": [],
                "scene_location": "未知",
                "atmosphere": {},
                "error": "JSON Parse Error"
            }
        except Exception as e:
            print(f"   ⚠️ Editor 运行错误: {e}")
            return {
                "title": "错误",
                "outline": [f"系统错误: {str(e)}"],
                "active_characters": [],
                "scene_location": "未知",
                "atmosphere": {}
            }