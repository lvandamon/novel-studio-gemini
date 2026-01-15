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
        flashback_injection = st.text_area("💉 记忆/闪回注入 (Flashback Injection)", placeholder="在此输入一段过去的记忆或强烈的情感片段，系统将强制在文中闪回...", height=100)
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
            "director_ran": force_director, # Hint
            "flashback_injection": flashback_injection if flashback_injection.strip() else None
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
                
                # Check for intervention
                if result.get("intervention_reason"):
                    st.error("🛑 流程中断：需要人工干预")
                    st.warning(f"原因: {result.get('intervention_reason')}")
                    st.info("请在下方【干扰参数】中调整指令，或在【数据修正】页签中修复逻辑冲突，然后重新运行。")
                elif result.get("final_content"):
                    st.session_state.current_content = result.get("final_content", "（无内容生成）")
                    st.success("✅ 生成完成！已自动归档。")
                else:
                    st.warning("⚠️ 流程结束但未生成内容 (可能被手动中止)")
                
            except Exception as e:
                sys.stdout = old_stdout # restore
                st.error(f"❌ 工作流出错: {e}")
                st.session_state.logs.append(f"ERROR: {e}")
            finally:
                st.session_state.workflow_running = False
                # st.rerun() # Don't rerun immediately so user can see error

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
tab1, tab2, tab3, tab4 = st.tabs(["📚 历史章节", "🕸️ 知识图谱", "🕵️ 伏笔看板", "🛠️ 数据修正 (Retcon)"])

with tab1:
    chap_num_view = st.number_input("查看章节", min_value=1, max_value=max(1, next_chap-1), step=1)
    if st.button("加载章节"):
        summary = memory.get_chapter_summary(chap_num_view)
        st.markdown(f"**摘要**: {summary}")

with tab2:
    st.markdown("### 🌌 实体关系网")
    if st.button("渲染图谱 (Neo4j)"):
        with st.spinner("Fetching Graph Data..."):
            try:
                graph_data = memory.get_visual_graph_data(limit=150)
                if graph_data["nodes"]:
                    # Create PyVis Network
                    net = Network(height="600px", width="100%", bgcolor="#1e1e1e", font_color="white", select_menu=True, filter_menu=True)
                    
                    # Add nodes
                    for n in graph_data["nodes"]:
                        net.add_node(n["id"], label=n["label"], title=n["label"], color=n["color"], group=n["group"])
                    
                    # Add edges
                    for e in graph_data["edges"]:
                        net.add_edge(e["from"], e["to"], label=e["label"], title=e["label"], arrows=e["arrows"])
                    
                    # Physics options
                    net.set_options("""
                    var options = {
                      "physics": {
                        "barnesHut": {
                          "gravitationalConstant": -3000,
                          "springLength": 200
                        }
                      }
                    }
                    """)
                    
                    # Save and display
                    # Use a unique name to prevent caching issues
                    path = os.path.join(os.getcwd(), "pages", "graph.html")
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    net.save_graph(path)
                    
                    with open(path, 'r', encoding='utf-8') as f:
                        source_code = f.read()
                    components.html(source_code, height=620)
                else:
                    st.warning("暂无图谱数据。")
            except Exception as e:
                st.error(f"图谱渲染失败: {e}")

with tab3:
    st.markdown("### 🧩 伏笔管理 (Chekhov's Gun)")
    
    # 1. Stale Hooks
    st.markdown("#### ⚠️ 陈旧伏笔 (Stale Hooks)")
    stale_hooks = memory.get_stale_unresolved_hooks(limit=10)
    if stale_hooks:
        for h in stale_hooks:
            with st.expander(f"[Ch{h['chapter_created']}] {h['content'][:50]}...", expanded=True):
                st.write(f"**内容**: {h['content']}")
                st.write(f"**重要性**: {h['importance']}")
                if st.button(f"强制回收 (Resolve #{h['id']})", key=f"res_{h['id']}"):
                    memory.resolve_foreshadowing(h['id'], next_chap, confidence=1.0)
                    st.success("已标记为已回收！")
                    st.rerun()
    else:
        st.info("暂无严重滞后的伏笔。")
        
    st.divider()
    
    # 2. All Active Hooks
    with st.expander("查看所有活跃伏笔"):
        all_hooks = memory.get_active_foreshadowing()
        df_hooks = pd.DataFrame(all_hooks)
        if not df_hooks.empty:
            st.dataframe(df_hooks[['chapter_created', 'content', 'importance', 'status']])

with tab4:
    st.markdown("### 🧬 角色档案修正 (Character Retcon)")
    st.info("直接修改数据库中的角色状态。请谨慎操作，修改后无法撤销。")
    
    # Load all characters
    import sqlite3
    import json
    
    conn = sqlite3.connect(memory.db_path)
    df_chars = pd.read_sql("SELECT id, name, data FROM characters", conn)
    conn.close()
    
    # Convert JSON data to columns for editing
    # Simplified: just show name and raw JSON for advanced editing, 
    # or extract key fields.
    # For Retcon, raw JSON editing is powerful but dangerous.
    # Let's try to extract some common fields.
    
    char_list = []
    for _, row in df_chars.iterrows():
        try:
            d = json.loads(row['data'])
            char_list.append({
                "id": row['id'],
                "name": row['name'],
                "role": d.get("role", "NPC"),
                "status": d.get("current_state", "Normal"),
                "location": d.get("location", "Unknown"),
                "level": d.get("level", "Unknown"),
                "is_dead": d.get("is_dead", False)
            })
        except:
            pass
            
    df_editor = pd.DataFrame(char_list)
    
    edited_df = st.data_editor(df_editor, num_rows="dynamic", key="char_editor")
    
    if st.button("💾 保存角色修正"):
        # Detect changes and update DB
        # This is a bit complex logic-wise for a demo, 
        # basically we iterate edited_df, find changes, and update JSON in DB.
        # For now, let's just support updating the fields shown.
        
        conn = sqlite3.connect(memory.db_path)
        cursor = conn.cursor()
        
        updated_count = 0
        for index, row in edited_df.iterrows():
            cid = row['id']
            # Fetch original
            cursor.execute("SELECT data FROM characters WHERE id = ?", (cid,))
            orig_row = cursor.fetchone()
            if orig_row:
                orig_data = json.loads(orig_row[0])
                # Update fields
                orig_data['role'] = row['role']
                orig_data['current_state'] = row['status']
                orig_data['location'] = row['location']
                orig_data['level'] = row['level']
                orig_data['is_dead'] = row['is_dead']
                
                new_json = json.dumps(orig_data, ensure_ascii=False)
                cursor.execute("UPDATE characters SET data = ? WHERE id = ?", (new_json, cid))
                updated_count += 1
        
        conn.commit()
        conn.close()
        st.success(f"已更新 {updated_count} 名角色的档案。")
        st.rerun()
