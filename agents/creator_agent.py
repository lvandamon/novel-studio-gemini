import json
import re
from typing import Dict, Any, List
from langchain_core.output_parsers import StrOutputParser
from core.llm import get_deepseek_chat
from core.prompts import (
    NOVEL_PROPOSAL_PROMPT, 
    CHARACTER_GENERATION_PROMPT, 
    VOLUME_MAP_PROMPT, 
    CHAPTER_OUTLINE_PROMPT
)

class CreatorAgent:
    def __init__(self):
        self.llm = get_deepseek_chat(temperature=0.7) # High temp for creativity
        
        self.proposal_chain = NOVEL_PROPOSAL_PROMPT | self.llm | StrOutputParser()
        self.char_chain = CHARACTER_GENERATION_PROMPT | self.llm | StrOutputParser()
        self.vol_map_chain = VOLUME_MAP_PROMPT | self.llm | StrOutputParser()
        self.chapter_chain = CHAPTER_OUTLINE_PROMPT | self.llm | StrOutputParser()

    def _clean_json(self, text: str) -> str:
        """Helper to extract JSON from LLM output"""
        text = text.strip()
        # Remove markdown code blocks
        if "```json" in text:
            text = re.search(r'```json\s*(\{.*\}|\[.*\])\s*```', text, re.DOTALL).group(1)
        elif "```" in text:
            text = text.replace("```", "")
            
        # Remove single-line comments // ...
        text = re.sub(r'//.*', '', text)
        
        # Remove trailing commas (simple case)
        text = re.sub(r',\s*([\]\}])', r'\1', text)
            
        return text.strip()

    def generate_proposal(self, genre: str, tone: str, ending: str, perspective: str) -> Dict[str, Any]:
        print("✨ Creator: 正在构思小说提案...")
        response = self.proposal_chain.invoke({
            "genre": genre,
            "tone": tone,
            "ending": ending,
            "perspective": perspective
        })
        try:
            return json.loads(self._clean_json(response))
        except Exception as e:
            print(f"⚠️ JSON Parse Error: {e}")
            return {"error": str(e), "raw": response}

    def generate_characters(self, proposal: Dict[str, Any]) -> List[Dict[str, Any]]:
        print("👥 Creator: 正在设计角色班底...")
        response = self.char_chain.invoke({
            "title": proposal.get("title"),
            "setting": proposal.get("setting"),
            "core_conflict": proposal.get("core_conflict")
        })
        try:
            return json.loads(self._clean_json(response))
        except Exception as e:
            print(f"⚠️ JSON Parse Error: {e}")
            return []

    def generate_volume_map(self, proposal: Dict[str, Any]) -> List[Dict[str, Any]]:
        print("🗺️ Creator: 正在规划全书骨架...")
        response = self.vol_map_chain.invoke({
            "title": proposal.get("title"),
            "core_conflict": proposal.get("core_conflict"),
            "ending_design": proposal.get("ending_design")
        })
        try:
            return json.loads(self._clean_json(response))
        except Exception as e:
            print(f"⚠️ JSON Parse Error: {e}")
            return []

    def generate_volume_outline(self, volume_info: Dict[str, Any], proposal: Dict[str, Any], chapter_count: int = 50) -> List[Dict[str, Any]]:
        print(f"📜 Creator: 正在推演 [{volume_info['title']}] 的章节细纲...")
        response = self.chapter_chain.invoke({
            "title": proposal.get("title"),
            "volume_name": volume_info['title'],
            "volume_goal": volume_info['goal'],
            "volume_summary": volume_info['summary'],
            "chapter_count": chapter_count
        })
        try:
            return json.loads(self._clean_json(response))
        except Exception as e:
            print(f"⚠️ JSON Parse Error: {e}")
            return []
