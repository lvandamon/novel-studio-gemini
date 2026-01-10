import streamlit as st
import os
import re
import json
import pandas as pd
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from core.memory import MemoryManager
from core.context_manager import ContextManager
from core.prompts import MASTER_SYSTEM_PROMPT
from agents.writer_agent import WriterAgent
from agents.editor_agent import EditorAgent
from agents.archivist_agent import ArchivistAgent
from agents.reviewer_agent import ReviewerAgent
from agents.foreshadowing_agent import ForeshadowingAgent

# --- 0. 全局配置 ---
st.set_page_config(
    page_title="DeepSeek Novel Studio - 清风揽岳", 
    page_icon="🏔️", 
    layout="wide",
    initial_sidebar_state="expanded"
)
load_dotenv()

# --- 1. 资源与状态初始化 (Cached) ---

@st.cache_resource
def get_memory_manager():
    return MemoryManager()

@st.cache_resource
def get_agents(_memory):
    return {
        "editor": EditorAgent(),
        "writer": WriterAgent(),
        "reviewer": ReviewerAgent(_memory),
        "archivist": ArchivistAgent(_memory),
        "fore_shadow": ForeshadowingAgent(_memory)
    }

@st.cache_resource
def get_context_manager(_memory):
    return ContextManager(_memory)

# 获取核心实例
memory = get_memory_manager()
context_manager = get_context_manager(memory)
agents = get_agents(memory)

# 初始化 Session State
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_outline" not in st.session_state:
    st.session_state.current_outline = None
if "current_chapter_text" not in st.session_state:
    st.session_state.current_chapter_text = ""
if "current_review" not in st.session_state:
    st.session_state.current_review = ""
if "generation_log" not in st.session_state:
    st.session_state.generation_log = [] # 记录生成过程的日志

# --- 2. 辅助函数 ---

def log_to_ui(message, level="info"):
    """将后台日志推送到前端 session"""
    icon = "ℹ️"
    if level == "success": icon = "✅"
    elif level == "warning": icon = "⚠️"
    elif level == "error": icon = "❌"
    elif level == "thinking": icon = "🧠"
    elif level == "writing": icon = "✍️"
    
    st.session_state.generation_log.append(f"{icon} {message}")

def get_chat_llm():
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
        base_url="https://api.deepseek.com/v1",
        temperature=0.7,
        streaming=True
    )

def handle_generate_chapter(chapter_num: int):
    """核心工作流：生成指定章节"""
    st.session_state.generation_log = [] # 清空日志
    progress_bar = st.progress(0, text="启动引擎...")
    
    try:
        # 0. 准备阶段
        log_to_ui(f"开始生成第 {chapter_num} 章...", "info")
        prev_summary = memory.get_chapter_summary(chapter_num - 1)
        if prev_summary == "暂无摘要。": prev_summary = "（首章或无前情，自动推演）"
        
        # 1. Editor (R1) - 制定大纲
        progress_bar.progress(20, text="DeepSeek-R1: 正在思考叙事节拍与细纲...")
        log_to_ui("主编正在审视全局状态 (Focus) 与历史记忆...", "thinking")
        
        editor_ctx = context_manager.build_editor_context(chapter_num, prev_summary)
        outline_data = agents["editor"].generate_outline(editor_ctx, chapter_num)
        
        st.session_state.current_outline = outline_data # 存入 State
        log_to_ui(f"大纲已锁定: {outline_data.get('title', '无标题')}", "success")
        log_to_ui(f"叙事重心: {outline_data.get('narrative_focus', 'N/A')}", "info")
        
        # 2. Writer (V3) - 撰写正文
        progress_bar.progress(50, text="DeepSeek-V3: 正在挥毫泼墨...")
        log_to_ui("作家正在根据大纲和联想记忆进行创作...", "writing")
        
        writer_ctx = context_manager.build_writer_context(
            str(outline_data.get('outline', '')), 
            outline_data.get('active_characters', [])
        )
        content = agents["writer"].write_chapter(str(outline_data.get('outline', '')), writer_ctx)
        
        st.session_state.current_chapter_text = f"# 第 {chapter_num} 章 {outline_data.get('title', '')}\n\n{content}"
        log_to_ui(f"正文创作完成，共 {len(content)} 字。", "success")
        
        # 3. Reviewer (R1) - 审核
        progress_bar.progress(70, text="DeepSeek-R1: 毒舌书评人正在挑刺...")
        log_to_ui("书评人正在进行逻辑一致性检查...", "thinking")
        
        feedback = agents["reviewer"].review_draft(content)
        st.session_state.current_review = feedback
        
        if "PASS" in feedback.upper():
            log_to_ui("审核通过！逻辑自洽。", "success")
        else:
            log_to_ui("审核提出修改意见 (已记录)", "warning")
            
        # 4. Archivist & Foreshadowing (V3) - 归档
        progress_bar.progress(90, text="DeepSeek-V3: 正在整理档案与伏笔...")
        log_to_ui("正在提取新设定与事件...", "info")
        
        agents["archivist"].archive_chapter(content, chapter_num)
        hook_data = agents["fore_shadow"].analyze_hooks(content, chapter_num)
        
        new_clues = hook_data.get("new_clues", [])
        if new_clues:
            for clue in new_clues:
                log_to_ui(f"埋下新伏笔: {clue}", "warning")
                
        # 简单更新摘要 (实际可用 Summarizer)
        memory.update_chapter_summary(chapter_num, f"{outline_data.get('title')} - 详情见正文")
        
        progress_bar.progress(100, text="完成")
        st.toast(f"第 {chapter_num} 章生成完毕！")
        
    except Exception as e:
        log_to_ui(f"生成过程出错: {str(e)}", "error")
        st.error(f"Error: {e}")
        import traceback
        print(traceback.format_exc())

# --- 3. 界面布局 ---

# Header
st.title("🏔️ DeepSeek Novel Studio")
st.caption("基于 DeepSeek R1/V3 双模型的长篇小说创作系统 | 动态记忆 | 节拍控制 | 自动归档")

# Sidebar: Controls
with st.sidebar:
    st.header("🎛️ 控制台")
    api_key = st.text_input("DeepSeek API Key", value=os.environ.get("DEEPSEEK_API_KEY", ""), type="password")
    if api_key: os.environ["DEEPSEEK_API_KEY"] = api_key
    
    st.markdown("---")
    st.subheader("📚 连载管理")
    # 自动计算下一章章节号
    # (简单起见，这里手动输入，未来可以从 DB 读取 max chapter)
    target_chapter = st.number_input("目标章节号", min_value=1, value=1)
    
    if st.button("🚀 生成该章节", type="primary", use_container_width=True):
        if not api_key:
            st.error("请先设置 API Key")
        else:
            handle_generate_chapter(target_chapter)
            
    st.markdown("---")
    st.subheader("🛠️ 调试工具")
    if st.button("🧹 重置所有数据 (慎用)"):
        # 简单粗暴删文件
        try:
            if os.path.exists("data/novel.db"): os.remove("data/novel.db")
            import shutil
            if os.path.exists("data/vector_store"): shutil.rmtree("data/vector_store")
            st.cache_resource.clear()
            st.success("数据已清空，请刷新页面。")
        except Exception as e:
            st.error(f"清空失败: {e}")

# Main Area
col_left, col_right = st.columns([0.4, 0.6])

# --- 左侧：战略视图 (Dashboard & Chat) ---
with col_left:
    # 1. 顶部仪表盘 (Dashboard)
    st.subheader("📊 叙事仪表盘 (Narrative Dashboard)")
    focus = memory.get_narrative_focus()
    
    # 使用 Metric 卡片展示关键信息
    m1, m2 = st.columns(2)
    m1.metric("当前卷 (Volume)", focus.get("volume", "未定义"))
    m2.metric("当前单元 (Arc)", focus.get("arc", "未定义"))
    
    st.info(f"**当前节拍 (Beat)**: {focus.get('beat', '未定义')}")
    st.warning(f"**核心冲突**: {focus.get('conflict', 'N/A')}")
    
    with st.expander("查看完整世界状态"):
        st.write(f"**当前目标**: {focus.get('goal')}")
        st.write(f"**世界动态**: {focus.get('state')}")
        
    st.markdown("---")
    
    # 2. 对话助手 (Chat)
    st.subheader("💬 创作助理 (Chat Assistant)")
    chat_container = st.container(height=400)
    
    # 初始化欢迎语
    if not st.session_state.messages:
        st.session_state.messages.append({"role": "assistant", "content": "我是清风揽岳。您可以直接在上方点击【生成章节】，或在这里与我讨论剧情。"})

    with chat_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                
    if prompt := st.chat_input("输入剧情想法或指令..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with chat_container:
            st.chat_message("user").markdown(prompt)
            
        # 简单对话逻辑 (不涉及复杂 Agent 调用，仅作为陪聊)
        # 如果需要复杂功能，这里应该调用 Master Agent
        llm = get_chat_llm()
        try:
            history = [SystemMessage(content=MASTER_SYSTEM_PROMPT)] + \
                      [HumanMessage(content=m["content"]) if m["role"] == "user" else AIMessage(content=m["content"]) for m in st.session_state.messages]
            
            with st.chat_message("assistant"):
                stream = llm.stream(history)
                response = st.write_stream(stream)
            st.session_state.messages.append({"role": "assistant", "content": response})
        except Exception as e:
            st.error(f"对话出错: {e}")


# --- 右侧：战术视图 (Tactical View) ---
with col_right:
    st.subheader("📝 创作工作台")
    
    # 使用 Tabs 分隔不同层级的信息
    tab_log, tab_content, tab_outline, tab_data = st.tabs(["⚡️ 生成日志", "📄 正文预览", "📋 章节大纲", "🗃️ 资料库"])
    
    with tab_log:
        st.caption("系统运行实时日志")
        if st.session_state.generation_log:
            for log in st.session_state.generation_log:
                st.markdown(log)
        else:
            st.info("暂无生成日志，请点击左侧【生成该章节】开始。")
            
    with tab_content:
        if st.session_state.current_chapter_text:
            st.markdown(st.session_state.current_chapter_text)
            if st.session_state.current_review:
                with st.expander("🧐 查看审核报告"):
                    st.markdown(st.session_state.current_review)
        else:
            st.write("暂无正文内容。")
            
    with tab_outline:
        if st.session_state.current_outline:
            st.json(st.session_state.current_outline)
        else:
            st.write("暂无大纲数据。")
            
    with tab_data:
        # 展示角色和伏笔
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.markdown("**👥 角色列表**")
            chars = memory.get_all_characters_list()
            if chars:
                df = pd.DataFrame(chars)
                st.dataframe(df[["name", "role", "status"]], hide_index=True)
            else:
                st.caption("无数据")
                
        with col_d2:
            st.markdown("**🎣 活跃伏笔**")
            hooks = memory.get_active_foreshadowing()
            if hooks:
                for h in hooks:
                    st.markdown(f"- [第{h['chapter']}章] {h['content']}")
            else:
                st.caption("无数据")
