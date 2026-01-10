import streamlit as st
import os
import re
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate

from core.memory import MemoryManager
from core.prompts import MASTER_SYSTEM_PROMPT
from agents.writer_agent import WriterAgent
from agents.editor_agent import EditorAgent
from agents.archivist_agent import ArchivistAgent
from agents.reviewer_agent import ReviewerAgent

# --- 配置与初始化 ---
st.set_page_config(page_title="Novel Studio - 清风揽岳", page_icon="✍️", layout="wide")
load_dotenv()

# 初始化 Session State
if "messages" not in st.session_state:
    st.session_state.messages = []
if "memory" not in st.session_state:
    st.session_state.memory = MemoryManager()
if "agents_loaded" not in st.session_state:
    # 延迟加载 Agents (需要 API Key)
    st.session_state.agents_loaded = False

# --- 侧边栏 ---
with st.sidebar:
    st.title("⚙️ 设置")
    api_key = st.text_input("DeepSeek API Key", value=os.getenv("DEEPSEEK_API_KEY", ""), type="password")
    if api_key:
        os.environ["DEEPSEEK_API_KEY"] = api_key
    
    st.divider()
    st.subheader("📚 档案监控")
    chars = st.session_state.memory.get_all_characters_summary()
    st.text_area("角色状态", value=chars, height=300, disabled=True)
    
    if st.button("🗑️ 重置对话与记忆"):
        st.session_state.messages = []
        st.session_state.memory = MemoryManager() # 重置内存对象（注意：实际DB文件需手动清理或增强reset逻辑）
        st.rerun()

# --- 核心逻辑 ---

def get_main_llm():
    """获取主对话 LLM (DeepSeek-V3)"""
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com/v1",
        temperature=0.7,
        streaming=True
    )

def handle_command(command: str, user_input: str):
    """处理特殊指令"""
    # 提取章节号 (例如 "/章节 1", "/章节1", "/章节 第1章")
    chapter_match = re.search(r"/(?:章节|chapter)\s*(\d+)", user_input)
    
    if command == "章节" and chapter_match:
        chapter_num = int(chapter_match.group(1))
        return run_chapter_generation(chapter_num)
    
    if command == "角色开发":
        return run_character_development()

    return None

def run_chapter_generation(chapter_num: int):
    """后台运行章节生成工作流"""
    if not st.session_state.agents_loaded:
        st.session_state.editor = EditorAgent()
        st.session_state.writer = WriterAgent()
        st.session_state.reviewer = ReviewerAgent(st.session_state.memory)
        st.session_state.archivist = ArchivistAgent(st.session_state.memory)
        st.session_state.agents_loaded = True

    status_container = st.status(f"🚀 正在撰写第 {chapter_num} 章...", expanded=True)
    
    try:
        # 1. 获取上下文 (最近的对话历史作为 Summary/Context)
        # 这里简化处理：直接从 memory 中取最后几条，或者让 LLM 总结。
        # 为了演示，我们暂时假设用户在对话中已经铺垫好了，或者直接从 Memory RAG。
        summary = "（系统自动从上下文提取）承接上文剧情。" 
        context_str = st.session_state.memory.query_related_context(f"第 {chapter_num-1} 章")
        
        # 2. 生成大纲
        status_container.write("🕵️‍♂️ 主编正在构思大纲...")
        outline = st.session_state.editor.generate_outline(summary, context_str, chapter_num)
        
        # 3. 撰写正文
        status_container.write("✍️ 作家正在挥毫泼墨 (3000字目标)...")
        settings = st.session_state.memory.get_all_characters_summary()
        content = st.session_state.writer.write_chapter(outline, settings)
        
        # 4. 审核
        status_container.write("🧐 书评人正在审核...")
        review = st.session_state.reviewer.review_draft(content)
        
        # 5. 归档
        status_container.write("🗄️ 档案员正在入库...")
        st.session_state.archivist.archive_chapter(content, chapter_num)
        
        status_container.update(label="✅ 章节创作完成！", state="complete")
        
        return f"""[系统提示] 第 {chapter_num} 章已生成并归档。

**大纲**：
{outline}

**审核意见**：
{review}

**正文预览** (前500字)：
{content[:500]}...

(完整正文已存入数据库，请继续下一章或提出修改意见。)
"""
    except Exception as e:
        status_container.update(label="❌ 生成失败", state="error")
        return f"[系统错误] 章节生成失败: {e}"

def run_character_development():
    """提取当前对话中的角色信息入库"""
    # 这里可以做一个高级功能：让 LLM 分析之前的对话历史，提取角色表
    # 简化版：提示用户手动输入或解析最近的消息
    return "[系统提示] 角色开发功能已激活。我会持续监控对话中的角色设定并自动更新到档案中。(此功能主要由后台档案员自动完成，您可以在对话中直接列出角色表)"

# --- 主界面渲染 ---

st.title("Novel Studio: 清风揽岳")
st.caption("“我是清风揽岳，你的专属金牌作家。”")

# 1. 显示历史消息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 2. 初始引导 (如果历史为空)
if not st.session_state.messages and api_key:
    # 发送 System Prompt 并请求自我介绍
    llm = get_main_llm()
    try:
        # 为了让 System Prompt 生效，我们需要把它作为第一条消息，但通常 Chat 界面不显示 System Message
        # 我们手动触发一次 AI 回复
        messages = [
            SystemMessage(content=MASTER_SYSTEM_PROMPT),
            HumanMessage(content="请开始自我介绍，并进入[小说设定]环节。")
        ]
        
        with st.chat_message("assistant"):
            stream = llm.stream(messages)
            response = st.write_stream(stream)
        
        st.session_state.messages.append({"role": "assistant", "content": response})
    except Exception as e:
        st.error(f"连接失败: {e}")

# 3. 用户输入处理
if prompt := st.chat_input("输入你的想法或指令 (如 /章节 1)..."):
    if not api_key:
        st.error("请先设置 API Key")
        st.stop()

    # 显示用户消息
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 检查是否是指令
    response_content = ""
    command_response = None
    
    if prompt.startswith("/"):
        cmd_type = prompt.split()[0].replace("/", "") # 提取指令词
        command_response = handle_command(cmd_type, prompt)
    
    # 如果有指令执行结果，直接显示结果（或者作为系统上下文喂给 AI 继续聊）
    if command_response:
        with st.chat_message("assistant"):
            st.markdown(command_response)
        st.session_state.messages.append({"role": "assistant", "content": command_response})
    else:
        # 常规对话：调用主 LLM
        llm = get_main_llm()
        
        # 构造消息历史 (包含 System Prompt)
        history = [SystemMessage(content=MASTER_SYSTEM_PROMPT)]
        for m in st.session_state.messages:
            if m["role"] == "user":
                history.append(HumanMessage(content=m["content"]))
            else:
                history.append(AIMessage(content=m["content"]))
        
        with st.chat_message("assistant"):
            stream = llm.stream(history)
            response_content = st.write_stream(stream)
        
        st.session_state.messages.append({"role": "assistant", "content": response_content})
        
        # 自动触发档案员 (可选：每次对话都检查是否有新设定)
        # st.session_state.archivist.archive_chapter(response_content, 0) # 暂不开启，避免太频繁
