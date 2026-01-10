import streamlit as st
import os
import re
import json
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
import streamlit.components.v1 as components

from core.memory import MemoryManager
from core.context_manager import ContextManager
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
if "context_manager" not in st.session_state:
    st.session_state.context_manager = ContextManager(st.session_state.memory)
if "agents_loaded" not in st.session_state:
    st.session_state.agents_loaded = False

# 新增：结构化数据存储
if "novel_toc" not in st.session_state:
    st.session_state.novel_toc = "暂无目录，请通过对话生成。"
if "current_chapter_content" not in st.session_state:
    st.session_state.current_chapter_content = "暂无章节内容。"
if "latest_review" not in st.session_state:
    st.session_state.latest_review = "暂无审核报告。"
if "char_relationship_graph" not in st.session_state:
    st.session_state.char_relationship_graph = """
    graph TD
    A[主角] -->|未知关系| B[?]
    """

# --- 辅助函数 ---

def get_main_llm():
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com/v1",
        temperature=0.7,
        streaming=True
    )

def extract_code_block(text, label):
    """从文本中提取指定标签的代码块内容 (用于提取目录或Mermaid)"""
    # 简单正则提取 ```label ... ```
    pattern = rf"```{{label}}\s*(.*?)"""
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    return None

def handle_command(command: str, user_input: str):
    """处理特殊指令"""
    # 提取章节号
    chapter_match = re.search(r"/(?:章节|chapter)\s*(\d+)", user_input)
    
    if command == "章节" and chapter_match:
        chapter_num = int(chapter_match.group(1))
        return run_chapter_generation(chapter_num)
    
    # 目录生成/更新指令（通常在对话中触发，这里作为手动触发入口）
    if command == "目录":
        return "[系统提示] 请在对话中直接要求我生成目录（例如：'请生成小说目录'）。我会自动识别并更新右侧面板。"

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
        # 1. 准备大纲上下文 (Tier 1 + Tier 3)
        summary = "（系统自动从上下文提取）承接上文剧情。" 
        # TODO: 从 Memory 中获取真实的 summary
        
        editor_ctx = st.session_state.context_manager.build_editor_context(chapter_num, summary)
        
        # 2. 大纲 (Editor)
        status_container.write("🕵️‍♂️ 主编正在构思大纲 (DeepSeek-R1)...")
        editor_output = st.session_state.editor.generate_outline(editor_ctx, chapter_num)
        
        outline_str = editor_output.get("outline", "生成失败")
        active_chars = editor_output.get("active_characters", [])
        
        status_container.write(f"📋 大纲已确认，本章登场：{', '.join(active_chars) if active_chars else '无特定角色'}")
        
        # 3. 准备正文上下文 (Tier 1 + Tier 2 + Tier 4)
        writer_ctx = st.session_state.context_manager.build_writer_context(outline_str, active_chars)
        
        # 4. 正文 (Writer)
        status_container.write("✍️ 作家正在挥毫泼墨 (DeepSeek-V3)...")
        content = st.session_state.writer.write_chapter(outline_str, writer_ctx)
        
        # 更新前端 State
        st.session_state.current_chapter_content = f"# 第 {chapter_num} 章\n\n{content}"
        
        # 5. 审核
        status_container.write("🧐 书评人正在审核...")
        review = st.session_state.reviewer.review_draft(content)
        st.session_state.latest_review = review
        
        # 6. 归档
        status_container.write("🗄️ 档案员正在入库...")
        st.session_state.archivist.archive_chapter(content, chapter_num)
        
        status_container.update(label="✅ 章节创作完成！请查看右侧预览。", state="complete")
        
        return f"""[系统提示] 第 {chapter_num} 章已生成。
**大纲摘要**：
{outline_str[:200]}...

**登场角色**：
{active_chars}

(完整正文及审核报告已同步至右侧面板)
"""
    except Exception as e:
        status_container.update(label="❌ 生成失败", state="error")
        import traceback
        return f"[系统错误] 章节生成失败: {e}\n{traceback.format_exc()}"

# --- 布局 ---

# Header
st.title("Novel Studio: 清风揽岳")

# 侧边栏：API Key 与设置
with st.sidebar:
    st.header("⚙️ 设置")
    api_key = st.text_input("DeepSeek API Key", value=os.getenv("DEEPSEEK_API_KEY", ""), type="password")
    if api_key:
        os.environ["DEEPSEEK_API_KEY"] = api_key
    
    if st.button("🗑️ 清空所有数据"):
        st.session_state.messages = []
        st.session_state.memory = MemoryManager()
        st.session_state.context_manager = ContextManager(st.session_state.memory)
        st.rerun()

# 主界面：左右分栏
col_chat, col_work = st.columns([0.4, 0.6])

# --- 左侧：对话控制台 ---
with col_chat:
    st.subheader("💬 创作助理")
    
    # 聊天历史容器
    chat_container = st.container(height=600)
    with chat_container:
        if not st.session_state.messages and api_key:
             # 初始引导
            llm = get_main_llm()
            try:
                messages = [SystemMessage(content=MASTER_SYSTEM_PROMPT), HumanMessage(content="请开始自我介绍，并进入[小说设定]环节。")]
                response = llm.invoke(messages).content
                st.session_state.messages.append({"role": "assistant", "content": response})
            except:
                pass

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # 输入框
    if prompt := st.chat_input("输入指令 (如 /章节 1) 或对话内容..."):
        if not api_key:
            st.error("请先设置 API Key")
            st.stop()

        st.session_state.messages.append({"role": "user", "content": prompt})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(prompt)

        # 指令处理
        command_response = None
        if prompt.startswith("/"):
            cmd_type = prompt.split()[0].replace("/", "")
            command_response = handle_command(cmd_type, prompt)

        if command_response:
            st.session_state.messages.append({"role": "assistant", "content": command_response})
            with chat_container:
                with st.chat_message("assistant"):
                    st.markdown(command_response)
            st.rerun() # 强制刷新以更新右侧面板
        else:
            # 普通对话
            llm = get_main_llm()
            history = [SystemMessage(content=MASTER_SYSTEM_PROMPT)]
            for m in st.session_state.messages:
                if m["role"] == "user": history.append(HumanMessage(content=m["content"]))
                else: history.append(AIMessage(content=m["content"]))
            
            with chat_container:
                with st.chat_message("assistant"):
                    stream = llm.stream(history)
                    response_content = st.write_stream(stream)
            
            st.session_state.messages.append({"role": "assistant", "content": response_content})
            
            # --- 智能解析 ---
            # 尝试从对话中提取 目录 和 关系图 并更新 State
            # 1. 提取 Mermaid
            mermaid_code = extract_code_block(response_content, "mermaid")
            if mermaid_code:
                st.session_state.char_relationship_graph = mermaid_code
                st.toast("检测到角色关系图更新！")
            
            # 2. 提取目录 (简单启发式：如果包含 "第x章"，且行数较多，认为是目录)
            if "小说目录" in response_content and "第" in response_content:
                st.session_state.novel_toc = response_content
                st.toast("检测到目录更新！")

            st.rerun()

# --- 右侧：工作台 ---
with col_work:
    st.subheader("🛠️ 实时工作台")
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📄 章节预览", "📑 目录大纲", "🎭 角色列表", "🕸️ 角色关系", "🌍 设定集"])
    
    with tab1:
        st.markdown(st.session_state.current_chapter_content)
        
    with tab2:
        st.markdown(st.session_state.novel_toc)
        
    with tab3:
        st.markdown("### 🎭 登场人物志")
        char_list = st.session_state.memory.get_all_characters_list()
        if char_list:
            import pandas as pd
            # 将 JSON 数据转为 DataFrame 格式展示
            df = pd.DataFrame(char_list)
            # 重新排序列名，使其更符合阅读习惯
            display_cols = ["name", "role", "personality", "status", "goal", "ability", "background"]
            # 过滤掉不存在的列
            available_cols = [c for c in display_cols if c in df.columns]
            if not available_cols: available_cols = df.columns
            
            st.dataframe(df[available_cols], use_container_width=True)
        else:
            st.info("暂无角色数据。请在对话中定义角色，或输入 `/章节` 让档案员自动提取。")
            
    with tab4:
        if st.session_state.char_relationship_graph:
            # 检查是否包含有效的 graphviz/mermaid 标记
            dot_content = st.session_state.char_relationship_graph
            if "graph" in dot_content or "digraph" in dot_content:
                st.graphviz_chart(dot_content)
            else:
                st.info("检测到关系图数据，但格式暂不支持直接渲染。请确保 AI 输出的是标准 Mermaid 或 Graphviz 格式。")
        else:
            st.info("暂无关系图，请在对话中要求生成。")
            
    with tab5:
        # 修改：使用 get_character_roster_brief 替代已删除的 get_all_characters_summary
        chars_brief = st.session_state.memory.get_character_roster_brief()
        st.markdown("### 🌍 世界观与全局设定")
        st.text_area("角色花名册 (Roster)", value=chars_brief, height=150)
        st.info("这里展示的是数据库中存储的精简花名册。")