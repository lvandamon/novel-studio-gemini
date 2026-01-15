import os
import time
from dotenv import load_dotenv

# 确保加载环境变量
load_dotenv()

from core.memory import MemoryManager
from core.context_manager import ContextManager
from agents.editor_agent import EditorAgent
from agents.writer_agent import WriterAgent
from agents.reviewer_agent import ReviewerAgent
from agents.archivist_agent import ArchivistAgent

def test_workflow():
    print("🚀 开始全流程核心逻辑测试...")
    
    # 1. 初始化
    print("\n[1] 初始化组件...")
    memory = MemoryManager()
    context_manager = ContextManager(memory)
    
    # 预埋一些假数据以便测试 RAG 和 Roster
    print("    -> 预埋测试数据...")
    memory.upsert_character("萧风", {"role": "主角", "status": "练气三层", "ability": "吞噬祖符"})
    memory.upsert_character("林月", {"role": "师妹", "status": "健康", "relationship": "暗恋萧风"})
    memory.add_chapter_context("萧风在后山捡到一枚黑色戒指，里面住着一个灵魂。", 1)
    
    # 2. 实例化 Agents
    editor = EditorAgent()
    writer = WriterAgent()
    reviewer = ReviewerAgent(memory)
    archivist = ArchivistAgent(memory)
    
    # 3. 模拟第 2 章生成流程
    chapter_num = 2
    print(f"\n[2] 模拟第 {chapter_num} 章生成...")
    
    # --- Context Manager ---
    print("\n   [Context] 组装 Editor 上下文...")
    summary = "第一章：萧风捡到戒指。"
    editor_ctx = context_manager.build_editor_context(chapter_num, summary)
    print(f"    -> Editor Context Preview:\n{editor_ctx[:200]}...")
    
    # --- Editor ---
    print("\n   [Editor] 生成大纲 (R1)...")
    # 这一步会真实调用 API，注意成本
    editor_output = editor.generate_outline(editor_ctx, chapter_num)
    print(f"    -> 解析结果: {editor_output.keys()}")
    print(f"    -> 在场角色: {editor_output.get('active_characters')}")
    
    outline = editor_output.get("outline", "默认大纲")
    active_chars = editor_output.get("active_characters", [])
    
    # --- Context Manager (Writer) ---
    print("\n   [Context] 组装 Writer 上下文...")
    writer_ctx = context_manager.build_writer_context(outline, active_chars)
    print(f"    -> Writer Context Preview (Length: {len(writer_ctx)} chars)...")
    
    # --- Writer ---
    print("\n   [Writer] 撰写正文 (V3)...")
    # 为了省钱/省时间，这里我们可以 Mock 一下，或者真实调用
    # 真实调用一下看看效果
    content = writer.write_chapter(outline, writer_ctx)
    print(f"    -> 正文生成完成 (长度: {len(content)} 字)")
    print(f"    -> 开头预览: {content[:100]}...")
    
    # --- Reviewer ---
    print("\n   [Reviewer] 审核稿件 (R1)...")
    # 这里会触发 Multi-Hop 检索
    review = reviewer.review_draft(content)
    print(f"    -> 审核意见:\n{review}")
    
    # --- Archivist ---
    print("\n   [Archivist] 归档数据...")
    archivist.archive_chapter(content, chapter_num)
    print("    -> 归档完成。")
    
    print("\n✅ 测试结束。")

if __name__ == "__main__":
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("❌ 错误: 未找到 DEEPSEEK_API_KEY")
    else:
        test_workflow()
