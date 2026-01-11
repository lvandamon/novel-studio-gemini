import streamlit as st
import os
import time
import tempfile
import pandas as pd
import streamlit.components.v1 as components
from pyvis.network import Network
from dotenv import load_dotenv

from core.memory import MemoryManager
from core.context_manager import ContextManager
from agents.writer_agent import WriterAgent
from agents.editor_agent import EditorAgent
from agents.archivist_agent import ArchivistAgent
from agents.reviewer_agent import ReviewerAgent
from agents.foreshadowing_agent import ForeshadowingAgent

# --- 0. 全局配置 & 样式 ---
st.set_page_config(
    page_title="DeepSeek Novel Studio Pro", 
    page_icon="🏔️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #f0f2f6; border-radius: 4px 4px 0px 0px; gap: 1px; padding-top: 10px; padding-bottom: 10px; }
    .stTabs [aria-selected="true"] { background-color: #ffffff; border-bottom: 2px solid #ff4b4b; }
    .reportview-container .main .block-container { max-width: 1200px; padding-top: 2rem; padding-bottom: 2rem; }
    div[data-testid="stExpander"] div[role="button"] p { font-size: 1.1rem; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

load_dotenv()

# --- 1. 核心单例模式 (Singleton Resource) ---
@st.cache_resource
def get_system_core():
    """初始化所有后端组件，全局唯一"""
    print("🚀 初始化 System Core...")
    memory = MemoryManager()
    ctx_mgr = ContextManager(memory)
    agents = {
        "editor": EditorAgent(),
        "writer": WriterAgent(),
        "reviewer": ReviewerAgent(memory),
        "archivist": ArchivistAgent(memory),
        "foreshadow": ForeshadowingAgent(memory)
    }
    return memory, ctx_mgr, agents

memory, context_manager, agents = get_system_core()

# --- 2. Session State 管理 (状态机) ---
# Workflow Stages: 0:Idle -> 1:Outline -> 2:Writing -> 3:Review -> 4:Archived
if "wf_stage" not in st.session_state: st.session_state.wf_stage = 0
if "current_chapter" not in st.session_state: st.session_state.current_chapter = 1

# Data Buffers (用于在不同阶段间传递数据)
if "buf_outline" not in st.session_state: st.session_state.buf_outline = {}
if "buf_content" not in st.session_state: st.session_state.buf_content = ""
if "buf_review" not in st.session_state: st.session_state.buf_review = ""

# UI Logs
if "logs" not in st.session_state: st.session_state.logs = []

def add_log(msg, level="info"):
    icon_map = {"info": "ℹ️", "success": "✅", "warn": "⚠️", "error": "❌", "ai": "🤖"}
    st.session_state.logs.append(f"{icon_map.get(level, '')} {msg}")

# --- 3. Sidebar: 全局控制台 ---
with st.sidebar:
    st.title("🏔️ Novel Studio")
    st.caption("DeepSeek R1/V3 Dual-Core Engine")
    
    api_key = st.text_input("API Key", type="password", value=os.getenv("DEEPSEEK_API_KEY", ""))
    if api_key: os.environ["DEEPSEEK_API_KEY"] = api_key
    
    st.divider()
    
    # 状态监控
    focus = memory.get_narrative_focus()
    st.markdown(f"**Current**: 第 {st.session_state.current_chapter} 章")
    st.info(f"📅 {focus.get('date', '未知日期')}")
    
    with st.expander("🌍 世界状态 (World State)", expanded=False):
        st.write(f"**卷**: {focus.get('volume')}")
        st.write(f"**节拍**: {focus.get('beat')}")
        st.write(f"**冲突**: {focus.get('conflict')}")
    
    st.divider()
    
    # 工具栏
    if st.button("🧹 清空当前 Session"):
        # for k in list(st.session_state.keys()):
        #     del st.session_state[k]
        st.session_state.clear()
        st.rerun()

# --- 4. Main Interface ---

st.title(f"Chapter {st.session_state.current_chapter}: {focus.get('volume', '新篇章')}")

# 进度条
steps = ["1. 构思 (Outline)", "2. 撰写 (Draft)", "3. 审核 (Review)", "4. 归档 (Archive)"]
current_step_idx = max(0, min(st.session_state.wf_stage - 1, 3)) if st.session_state.wf_stage > 0 else 0
st.progress((current_step_idx + 1) / 4, text=f"当前阶段: {steps[current_step_idx]}")

# 主要工作区
tab_main, tab_db, tab_settings = st.tabs(["📝 创作流", "🗃️ 档案室", "⚙️ 设置"])

# === Tab 1: 创作流 (The Workflow) ===
with tab_main:
    
    # Stage 0: 准备
    if st.session_state.wf_stage == 0:
        st.info("👋 准备好开始写下一章了吗？")
        col1, col2 = st.columns([1, 4])
        with col1:
            chap_num = st.number_input("章节号", value=st.session_state.current_chapter)
        with col2:
            st.write(" ") # Spacer
            if st.button("🚀 启动创作引擎 (Start Engine)", type="primary"):
                st.session_state.current_chapter = chap_num
                st.session_state.wf_stage = 1
                st.rerun()

    # Stage 1: 大纲 (Outline)
    elif st.session_state.wf_stage == 1:
        st.subheader("Step 1: 构思大纲 (Editor Agent)")
        
        # Action Area
        col_act, col_view = st.columns([1, 2])
        
        with col_act:
            st.markdown("主编 (DeepSeek-R1) 将根据前情提要和节拍生成细纲。")
            if st.button("💡 生成/重生成大纲"):
                with st.spinner("主编正在思考..."):
                    prev_sum = memory.get_chapter_summary(st.session_state.current_chapter - 1)
                    ctx = context_manager.build_editor_context(st.session_state.current_chapter, prev_sum)
                    outline = agents["editor"].generate_outline(ctx, st.session_state.current_chapter)
                    st.session_state.buf_outline = outline
                    add_log("大纲已生成", "success")
            
            if st.session_state.buf_outline:
                st.divider()
                st.success("大纲就绪！")
                if st.button("✅ 确认并进入撰写阶段", type="primary"):
                    st.session_state.wf_stage = 2
                    st.rerun()

        with col_view:
            if st.session_state.buf_outline:
                # 允许用户编辑大纲
                new_title = st.text_input("章节标题", value=st.session_state.buf_outline.get("title", ""))
                
                # 处理 outline 字段可能是 list 或 str
                raw_outline = st.session_state.buf_outline.get("outline", "")
                if isinstance(raw_outline, list):
                    raw_outline = "\n".join(raw_outline)
                
                new_outline_text = st.text_area("大纲内容 (可编辑)", value=raw_outline, height=300)
                
                # 实时回写
                st.session_state.buf_outline["title"] = new_title
                st.session_state.buf_outline["outline"] = new_outline_text

    # Stage 2: 撰写 (Writing)
    elif st.session_state.wf_stage == 2:
        st.subheader("Step 2: 撰写正文 (Writer Agent)")
        
        col_act, col_view = st.columns([1, 2])
        
        with col_act:
            st.markdown("作家 (DeepSeek-V3) 将基于大纲进行扩写。")
            
            # 上下文预览
            with st.expander("查看参考资料包"):
                active_chars = st.session_state.buf_outline.get("active_characters", [])
                st.write(f"**在场角色**: {active_chars}")
            
            if st.button("✍️ 生成初稿"):
                with st.spinner("作家正在挥毫泼墨..."):
                    outline_str = st.session_state.buf_outline.get("outline", "")
                    active_chars = st.session_state.buf_outline.get("active_characters", [])
                    
                    writer_ctx = context_manager.build_writer_context(str(outline_str), active_chars)
                    content = agents["writer"].write_chapter(str(outline_str), writer_ctx)
                    st.session_state.buf_content = content
                    add_log(f"正文生成完毕 ({len(content)}字)", "success")
            
            if st.session_state.buf_content:
                st.divider()
                if st.button("🔍 提交审核", type="primary"):
                    st.session_state.wf_stage = 3
                    st.rerun()

        with col_view:
            if st.session_state.buf_content:
                new_content = st.text_area("正文编辑器", value=st.session_state.buf_content, height=600)
                st.session_state.buf_content = new_content
            else:
                st.info("等待生成正文...")

    # Stage 3: 审核 (Review)
    elif st.session_state.wf_stage == 3:
        st.subheader("Step 3: 质量审核 (Reviewer Agent)")
        
        col_act, col_view = st.columns([1, 2])
        
        with col_act:
            if not st.session_state.buf_review:
                if st.button("🧐 开始审核"):
                    with st.spinner("书评人正在挑刺..."):
                        feedback = agents["reviewer"].review_draft(st.session_state.buf_content)
                        st.session_state.buf_review = feedback
                        add_log("审核完成", "success")
            
            if st.session_state.buf_review:
                is_pass = "PASS" in st.session_state.buf_review.upper()
                if is_pass:
                    st.success("审核通过！")
                else:
                    st.warning("发现潜在问题")
                
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    if st.button("🔙 返回修改"):
                        st.session_state.wf_stage = 2
                        st.session_state.buf_review = "" # 清除审核记录以便重审
                        st.rerun()
                with col_b2:
                    if st.button("📦 强制归档", type="primary"):
                        st.session_state.wf_stage = 4
                        st.rerun()

        with col_view:
            st.markdown("### 正文预览")
            st.text_area("正文内容", value=st.session_state.buf_content, height=200, disabled=True)
            
            if st.session_state.buf_review:
                st.markdown("### 审核报告")
                st.info(st.session_state.buf_review)

    # Stage 4: 归档 (Archiving)
    elif st.session_state.wf_stage == 4:
        st.subheader("Step 4: 自动归档 (Archivist Agent)")
        
        if st.button("💾 执行归档入库"):
            with st.spinner("正在提取数据、构建图谱、更新世界..."):
                try:
                    agents["archivist"].archive_chapter(st.session_state.buf_content, st.session_state.current_chapter)
                    add_log("归档完成", "success")
                    st.balloons()
                    
                    # Reset for next chapter
                    time.sleep(2)
                    st.session_state.current_chapter += 1
                    st.session_state.wf_stage = 0
                    st.session_state.buf_outline = {}
                    st.session_state.buf_content = ""
                    st.session_state.buf_review = ""
                    st.rerun()
                except Exception as e:
                    st.error(f"归档失败: {e}")

# === Tab 2: 档案室 (Database) ===
with tab_db:
    col_db1, col_db2 = st.columns([1, 1])
    
    with col_db1:
        st.markdown("### 👥 角色花名册")
        chars = memory.get_all_characters_list()
        if chars:
            st.dataframe(pd.DataFrame(chars))
            
    with col_db2:
        st.markdown("### 🕸️ 关系图谱")
        if st.button("🔄 刷新图谱"):
            graph_data = memory.get_visual_graph_data()
            if graph_data["nodes"]:
                net = Network(height="400px", width="100%", bgcolor="#ffffff", font_color="black")
                for n in graph_data["nodes"]:
                    net.add_node(n["id"], label=n["label"], color=n["color"], group=n["group"])
                for e in graph_data["edges"]:
                    net.add_edge(e["from"], e["to"], label=e["label"])
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
                    net.save_graph(tmp.name)
                    with open(tmp.name, 'r', encoding='utf-8') as f:
                        components.html(f.read(), height=420)

# === Tab 3: 设置 (Settings) ===
with tab_settings:
    st.markdown("### 🛠️ 系统维护")
    if st.button("⚠️ 重置 Narrative Focus (慎点)"):
        # Reset logic here
        pass