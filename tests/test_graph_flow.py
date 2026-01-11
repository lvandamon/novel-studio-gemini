import os
import sys
import time
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加项目根目录到 path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.memory import MemoryManager
from agents.archivist_agent import ArchivistAgent
from core.graph_store import GraphManager

# 模拟一段正文
TEST_CHAPTER_CONTENT = """
第1章：风起青云

萧风站在青云宗的山门前，紧握着手中的断剑。这把剑是他父亲萧远山留下的唯一遗物。
十八年前，萧远山是青云宗最年轻的长老，却因为爱上了魔教圣女叶红绫，被逐出师门。

“站住！”守门弟子赵铁柱冷笑道，“一个弃徒的野种，也配踏入我青云宗？”
赵铁柱是外门执事赵无极的侄子，平日里仗势欺人，与萧风素有积怨。

萧风眼中闪过一丝杀意，但他忍住了。他这次回来的目的只有一个：
找到当年的真相，洗清父亲的冤屈。

暗处，一个黑衣人默默注视着这一切。他是暗影阁的刺客“夜枭”，受雇于赵无极，目的是监视萧风的一举一动。
"""

def mock_add_triplet(source, source_type, relation, target, target_type, properties=None):
    """如果 Neo4j 没连接，用这个 Mock 函数打印本来要存的数据"""
    print(f"   [MOCK WRITE] Neo4j 未连接，但逻辑成功捕获: ({source}:{source_type}) --[{relation}]--> ({target}:{target_type}) | Props: {properties}")

def run_test():
    print("🚀 启动图谱流程测试...\n")

    # 1. 初始化记忆管理器
    print("1. 初始化 MemoryManager (SQLite + Chroma + Neo4j)...")
    memory = MemoryManager()
    
    # 检查图谱连接状态
    if not memory.graph.is_connected():
        print("⚠️  Neo4j 未连接。将使用 Mock 模式验证数据提取逻辑。\n")
        # Monkey patch 用于演示
        memory.graph.add_triplet = mock_add_triplet
    else:
        print("✅ Neo4j 已连接。数据将真实写入数据库。\n")

    # 2. 初始化归档员
    print("2. 初始化 ArchivistAgent...")
    archivist = ArchivistAgent(memory_manager=memory)

    # 3. 运行归档流程
    print(f"\n3. 正在处理测试章节 (模拟第 1 章)...")
    print("-" * 50)
    print(TEST_CHAPTER_CONTENT.strip())
    print("-" * 50)
    
    start_time = time.time()
    try:
        # 这里实际上会调用 LLM，可能会花十几秒
        archivist.archive_chapter(TEST_CHAPTER_CONTENT, chapter_num=1)
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return

    duration = time.time() - start_time
    print(f"\n✅ 归档完成，耗时: {duration:.2f}秒")

    # 4. 验证读取 (仅当连接真实存在时)
    if memory.graph.is_connected():
        print("\n4. 正在验证图谱读取 (Querying Graph)...")
        print("   查询 '萧风' 的社交关系网:")
        print("-" * 30)
        context = memory.get_social_graph("萧风")
        print(context)
        print("-" * 30)

        print("   查询 '赵无极' 的社交关系网:")
        print("-" * 30)
        context = memory.get_social_graph("赵无极")
        print(context)
        print("-" * 30)
    else:
        print("\n4. 跳过读取验证 (因为使用的是 Mock 模式)")

if __name__ == "__main__":
    run_test()
