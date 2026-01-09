import streamlit as st
import os
from dotenv import load_dotenv
from core.memory import MemoryManager
from agents.editor_agent import EditorAgent
from agents.writer_agent import WriterAgent
from agents.reviewer_agent import ReviewerAgent
from agents.archivist_agent import ArchivistAgent

# --- 页面配置 ---
st.set_page_config(
    page_title="Infinite-Flow Writer",
    page_icon="✍️",
    layout="wide"
)

# --- 初始化环境与 Session State ---
load_dotenv()

if "initialized" not in st.session_state:
    st.session_state.memory = MemoryManager()
    st.session_state.initialized = True
    st.session_state.logs = []

def add_log(msg):
    st.session_state.logs.append(msg)

# --- 侧边栏：配置与状态 ---
with st.sidebar:
    st.title("⚙️ 系统设置")
    api_key = st.text_input("DeepSeek API Key", 
                           value=os.getenv("DEEPSEEK_API_KEY", ""), 
                           type="password")
    if api_key:
        os.environ["DEEPSEEK_API_KEY"] = api_key
    
    st.divider()
    st.subheader("👥 角色档案")
    chars_summary = st.session_state.memory.get_all_characters_summary()
    st.text_area("当前已发现角色", value=chars_summary, height=200, disabled=True)
    
    if st.button("🗑️ 清空所有数据"):
        if st.checkbox("确认清空？"):
            # 简单实现：删除本地 db 文件（实际需更优雅）
            if os.path.exists("data/novel.db"): os.remove("data/novel.db")
            st.rerun()

# --- 主界面 ---
st.title("🎨 Infinite-Flow Writer")
st.caption("基于 DeepSeek R1 & V3 的智能小说创作系统")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📝 本章创作指令")
    chapter_num = st.number_input("章节序号", min_value=1, value=1)
    summary = st.text_area("核心冲突 (Summary)", placeholder="例如：林风在拍卖会中发现了一枚残破的古剑...", height=100)
    context = st.text_area("场景/前情提要 (Context)", placeholder="例如：拍卖行内，气氛焦灼，林风身边的青云剑微微颤动...", height=100)
    
    if st.button("🚀 开始创作", type="primary"):
        if not api_key:
            st.error("请输入 API Key！")
        elif not summary:
            st.warning("请输入核心冲突内容。")
        else:
            # 启动流程
            try:
                # 1. 初始化智能体
                with st.status("🤖 智能体正在协作...", expanded=True) as status:
                    editor = EditorAgent()
                    writer = WriterAgent()
                    reviewer = ReviewerAgent(st.session_state.memory)
                    archivist = ArchivistAgent(st.session_state.memory)
                    
                    # 2. 生成大纲
                    status.update(label="🕵️‍♂️ 主编 (R1) 正在拆解细纲...")
                    outline = editor.generate_outline(summary, context, chapter_num)
                    st.session_state.current_outline = outline
                    add_log(f"第 {chapter_num} 章大纲已生成")
                    
                    # 3. 撰写初稿
                    status.update(label="✍️ 作家 (V3) 正在撰写正文...")
                    settings = st.session_state.memory.get_all_characters_summary()
                    content = writer.write_chapter(outline, settings)
                    st.session_state.current_content = content
                    add_log(f"第 {chapter_num} 章初稿已生成")
                    
                    # 4. 逻辑审核
                    status.update(label="🧐 书评人 (R1) 正在审视逻辑...")
                    feedback = reviewer.review_draft(content)
                    st.session_state.current_review = feedback
                    
                    # 5. 归档处理
                    status.update(label="🗄️ 档案员正在更新数据库...")
                    archivist.archive_chapter(content, chapter_num)
                    
                    status.update(label="✅ 创作流程已完成！", state="complete")
                
                st.success("本章生成成功！")
            except Exception as e:
                st.error(f"运行出错: {e}")

with col2:
    st.subheader("📖 创作成果")
    
    tab1, tab2, tab3 = st.tabs(["正文预览", "章节大纲", "审核意见"])
    
    with tab1:
        if "current_content" in st.session_state:
            st.markdown(st.session_state.current_content)
        else:
            st.info("正文生成后将在此显示。")
            
    with tab2:
        if "current_outline" in st.session_state:
            st.markdown(st.session_state.current_outline)
            
    with tab3:
        if "current_review" in st.session_state:
            st.markdown(st.session_state.current_review)

# --- 底部日志 ---
st.divider()
with st.expander("🪵 系统运行日志"):
    for log in reversed(st.session_state.logs):
        st.write(f"- {log}")