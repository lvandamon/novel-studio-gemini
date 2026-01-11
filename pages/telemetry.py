import streamlit as st
import pandas as pd
import altair as alt
from core.memory import MemoryManager

st.set_page_config(page_title="Narrative Telemetry", page_icon="📈", layout="wide")

st.title("📈 防崩坏遥测仪表盘 (Narrative Telemetry)")
st.markdown("监控小说的各项生命体征，防止战力崩坏、风格漂移或逻辑雪崩。")

# Initialize Memory
memory = MemoryManager()

# Fetch Data
data = memory.get_metrics_history(limit=100) # Get all for now

if not data:
    st.info("暂无遥测数据。请先运行生成流程，Reviewer 将自动生成数据。")
else:
    df = pd.DataFrame(data)

    # --- 核心指标概览 (KPIs) ---
    latest = df.iloc[-1]
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("最新紧张度 (Tension)", f"{latest['tension']}/100", delta=int(latest['tension'] - df.iloc[-2]['tension']) if len(df) > 1 else 0)
    with col2:
        st.metric("最新压抑度 (Darkness)", f"{latest['darkness']}/100", delta=int(latest['darkness'] - df.iloc[-2]['darkness']) if len(df) > 1 else 0)
    with col3:
        st.metric("人设一致性", f"{latest['char_consistency']}/100", delta=int(latest['char_consistency'] - df.iloc[-2]['char_consistency']) if len(df) > 1 else 0)
    with col4:
        st.metric("逻辑严密性", f"{latest['plot_logic']}/100", delta=int(latest['plot_logic'] - df.iloc[-2]['plot_logic']) if len(df) > 1 else 0)

    st.divider()

    # --- 趋势分析 (Trends) ---
    
    # 1. 节奏与氛围 (Pacing & Atmosphere)
    st.subheader("1. 节奏与氛围 (Pacing & Atmosphere)")
    
    chart_atmosphere = alt.Chart(df).transform_fold(
        ['tension', 'darkness', 'pacing'],
        as_=['variable', 'value']
    ).mark_line(point=True).encode(
        x=alt.X('chapter:Q', title='Chapter'),
        y=alt.Y('value:Q', title='Score (0-100)'),
        color='variable:N',
        tooltip=['chapter:Q', 'variable:N', 'value:Q']
    ).properties(height=300)
    
    st.altair_chart(chart_atmosphere, width='stretch')

    # 2. 质量监控 (Consistency & Logic)
    st.subheader("2. 质量监控 (Quality Assurance)")
    
    chart_quality = alt.Chart(df).transform_fold(
        ['char_consistency', 'plot_logic'],
        as_=['variable', 'value']
    ).mark_line(point=True).encode(
        x=alt.X('chapter:Q', title='Chapter'),
        y=alt.Y('value:Q', scale=alt.Scale(domain=[0, 100]), title='Score'),
        color=alt.Color('variable:N', scale=alt.Scale(scheme='set2')),
        tooltip=['chapter:Q', 'variable:N', 'value:Q']
    ).properties(height=300)
    
    st.altair_chart(chart_quality, width='stretch')
    
    # --- 详细日志 ---
    st.subheader("3. 章节审计记录 (Audit Logs)")
    
    # 构造更详细的表格
    audit_view = df[['chapter', 'tension', 'darkness', 'char_consistency', 'plot_logic']].copy()
    
    # 获取每一章的 critique (需要修改 get_metrics_history 返回 critique，目前为了性能先不查)
    # 我们可以稍微 hack 一下，直接再查一次带 critique 的
    conn = memory.db_path
    import sqlite3
    con = sqlite3.connect(conn)
    critiques = pd.read_sql("SELECT chapter_num as chapter, critique FROM chapter_metrics", con)
    con.close()
    
    audit_view = pd.merge(audit_view, critiques, on='chapter')
    
    st.dataframe(
        audit_view,
        column_config={
            "critique": st.column_config.TextColumn("Reviewer Critique", width="large"),
            "tension": st.column_config.ProgressColumn("Tension", format="%d", min_value=0, max_value=100),
            "darkness": st.column_config.ProgressColumn("Darkness", format="%d", min_value=0, max_value=100),
            "char_consistency": st.column_config.NumberColumn("Char Sync", format="%d"),
        },
        width='stretch',
        hide_index=True
    )

