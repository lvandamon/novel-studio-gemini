import streamlit as st

st.set_page_config(page_title="Infinite-Flow Writer", page_icon="✍️")

st.title("Infinite-Flow Writer (DeepSeek Edition)")
st.sidebar.title("设置")

st.write("欢迎使用无限流 AI 写作系统。")

api_key = st.sidebar.text_input("DeepSeek API Key", type="password")

if not api_key:
    st.info("请在侧边栏输入 DeepSeek API Key 以继续。")
else:
    st.success("API Key 已就绪。")
