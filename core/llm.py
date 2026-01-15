import os
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

def get_deepseek_chat(temperature: float = 0.7) -> ChatOpenAI:
    """
    返回 DeepSeek-V3 (Chat) 模型实例。
    用于：正文撰写、场景描写、对话生成。
    """
    if not DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY not found in environment variables.")

    return ChatOpenAI(
        model="deepseek-chat",
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        temperature=temperature,
        streaming=True,
        max_retries=3,
        request_timeout=120
    )

def get_deepseek_reasoner() -> ChatOpenAI:
    """
    返回 DeepSeek-R1 (Reasoner) 模型实例。
    用于：剧情推演、大纲拆解、逻辑检查。
    注意：Reasoner 模型通常不建议设置较高的 temperature，且可能不支持 system prompt（视具体 API 实现而定，DeepSeek 兼容层通常支持）。
    """
    if not DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY not found in environment variables.")

    return ChatOpenAI(
        model="deepseek-reasoner",
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        # R1 推荐 temperature 为 0 以保证逻辑严密性。
        temperature=0.0, 
        streaming=True,
        max_retries=3,
        request_timeout=300 # R1 needs more time to think
    )
