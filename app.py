import streamlit as st
import os
import io
import contextlib
import time
import pandas as pd
import streamlit.components.v1 as components
from pyvis.network import Network
from dotenv import load_dotenv

from core.memory import MemoryManager
from core.workflow import NovelWorkflow

# --- 0. 全局配置 ---
st.set_page_config(
    page_title="DeepSeek Novel Studio Pro", 
    page_icon="🏔️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for log stream
st.markdown("""
<style>
    .log-container {
        font-family: 'Courier New', monospace;
        font-size: 0.85em;
        background-color: #f8f9fa;
        padding: 10px;
        border-radius: 5px;
        height: 400px;
        overflow-y: auto;
        border: 1px solid #ddd;
    }
</style>
""", unsafe_allow_html=True)

load_dotenv()

# --- 1. Core Initialization ---
@st.cache_resource
def get_system():
    """Initialize system components"""
    print("🚀 Initializing Novel Studio System...")
    memory = MemoryManager()
    workflow = NovelWorkflow(memory)
    return memory, workflow

memory, workflow = get_system()

# --- 2. Session State ---
if "logs" not in st.session_state: st.session_state.logs = []
if "current_content" not in st.session_state: st.session_state.current_content = ""
if "current_focus" not in st.session_state: st.session_state.current_focus = {}
if "workflow_running" not in st.session_state: st.session_state.workflow_running = False

# Capture stdout for logs
@contextlib.contextmanager
def capture_output():
    new_out = io.StringIO()
    # In a real multi-user web app, capturing stdout is tricky.
    # For a local single-user Streamlit app, this is acceptable.
    # We will try to redirect print statements to our log buffer.
    
    # We simply monkey-patch print? No, that's dangerous.
    # We will rely on our nodes explicitly printing to stdout 
    # and we won't capture it here perfectly due to threading.
    # Instead, we'll append to session_state.logs inside the tool calls if possible,
    # OR we rely on the return values.
    
    # Actually, let's just use a simple redirect for the duration of the function call
    yield new_out

# --- 3. Sidebar ---
with st.sidebar:
    st.title("🏔️ Novel Studio")
    st.caption("Auto-Novel Generation System")
    
    # Focus Monitor
    focus = memory.get_narrative_focus()
    st.session_state.current_focus = focus
    
    st.markdown("### 🧭 叙事罗盘")
    st.info(f"Vol: {focus.get('volume')}")
    st.info(f"Arc: {focus.get('arc')}")
    st.warning(f"Beat: {focus.get('beat')}")
    
    st.divider()
    
    st.markdown("### 📊 进度")
    # Get last chapter num
    # Simple check: max chapter in DB
    try:
        # A bit hacky, normally should add a method to memory
        import sqlite3
        conn = sqlite3.connect(memory.db_path)
        cur = conn.cursor()
        cur.execute("SELECT MAX(chapter_num) FROM chapters")
        row = cur.fetchone()
        last_chap = row[0] if row and row[0] else 0
        conn.close()
    except:
        last_chap = 0
        
    next_chap = last_chap + 1
    st.metric("下一章", f"第 {next_chap} 章")
    
    if st.button("🔄 刷新状态"):
        st.rerun()

# --- 4. Main Area ---

col_main, col_log = st.columns([2, 1])

with col_main:
    st.subheader(f"📝 生成控制台 (第 {next_chap} 章)")
    
    # Configuration
    with st.expander("🛠️ 干扰参数 (Intervention)", expanded=False):
        user_guidance = st.text_area("给导演/主编的额外指令 (可选)", placeholder="例如：本章必须要死一个配角...")
        force_director = st.checkbox("强制唤醒导演 (Force Director)", value=(next_chap % 5 == 0))
    
    # Action Button
    if st.button("🚀 生成下一章 (Auto-Run Workflow)", type="primary", disabled=st.session_state.workflow_running):
        st.session_state.workflow_running = True
        st.session_state.logs = [] # Clear logs
        
        # Prepare Input
        initial_state = {
            "chapter_num": next_chap,
            "narrative_plan": memory.get_active_plan(),
            "narrative_focus": memory.get_narrative_focus(),
            "revision_count": 0,
            "director_ran": force_director # Hint
        }
        
        # Run Graph
        app = workflow.build_graph()
        
        status_placeholder = st.empty()
        log_placeholder = col_log.empty()
        
        # Generator for streaming updates (LangGraph doesn't stream easily, so we wait)
        with st.spinner("流水线运转中... (预计耗时 1-2 分钟)"):
            try:
                # Capture print output hack
                import sys
                class StreamToLogger:
                    def write(self, buf):
                        for line in buf.rstrip().splitlines():
                            st.session_state.logs.append(line)
                            # Force refresh log view? hard in loop.
                    def flush(self):
                        pass
                
                old_stdout = sys.stdout
                sys.stdout = StreamToLogger()
                
                result = app.invoke(initial_state)
                
                sys.stdout = old_stdout
                
                st.session_state.current_content = result.get("final_content", "（无内容生成）")
                st.success("✅ 生成完成！已自动归档。")
                
            except Exception as e:
                sys.stdout = old_stdout # restore
                st.error(f"❌ 工作流出错: {e}")
                st.session_state.logs.append(f"ERROR: {e}")
            finally:
                st.session_state.workflow_running = False
                st.rerun()

    # Content Display
    if st.session_state.current_content:
        st.markdown("### 📄 最新章节预览")
        st.text_area("正文", value=st.session_state.current_content, height=600)

with col_log:
    st.subheader("📟 系统日志")
    log_text = "\n".join(st.session_state.logs)
    st.text_area("Logs", value=log_text, height=600, key="log_view", disabled=True)

# --- 5. Database View (Tabs below) ---
st.divider()
tab1, tab2 = st.tabs(["📚 历史章节", "🕸️ 知识图谱"])

with tab1:
    chap_num_view = st.number_input("查看章节", min_value=1, max_value=max(1, next_chap-1), step=1)
    if st.button("加载章节"):
        summary = memory.get_chapter_summary(chap_num_view)
        # Hack to get content from vector store (not ideal, but works for demo)
        docs = memory.similarity_search(f"第{chap_num_view}章正文", k=1) 
        # Better: query SQL events
        events = memory.get_relevant_events("", recent_k=10) # this is generic
        
        st.markdown(f"**摘要**: {summary}")
        # Content retrieval is hard without a direct 'chapters' table storing full text. 
        # Ideally we should add 'content' column to 'chapters' table in sqlite.

with tab2:
    if st.button("渲染图谱"):
        graph_data = memory.get_visual_graph_data()
        if graph_data["nodes"]:
            net = Network(height="500px", width="100%", bgcolor="#ffffff", font_color="black")
            for n in graph_data["nodes"]:
                net.add_node(n["id"], label=n["label"], color=n["color"], group=n["group"])
            for e in graph_data["edges"]:
                net.add_edge(e["from"], e["to"], label=e["label"])
            
            # Save and read
            net.save_graph("graph.html")
            with open("graph.html", 'r', encoding='utf-8') as f:
                components.html(f.read(), height=520)
