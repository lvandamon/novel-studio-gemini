import cmd
import os
import sys
import time
from typing import List, Dict, Any

from dotenv import load_dotenv

# Core
from core.memory import MemoryManager
from core.context_manager import ContextManager

# Agents
from agents.editor_agent import EditorAgent
from agents.writer_agent import WriterAgent
from agents.reviewer_agent import ReviewerAgent
from agents.archivist_agent import ArchivistAgent

# Utils
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_c(text: str, color: str = Colors.ENDC):
    print(f"{color}{text}{Colors.ENDC}")

class NovelStudioShell(cmd.Cmd):
    intro = f"""
{Colors.HEADER}================================================================
   Novel Studio Gemini (CLI Edition) v2.0
   基于 DeepSeek R1/V3 双核驱动
   
   输入 'help' 查看指令列表。输入 'status' 查看当前进度。
================================================================{Colors.ENDC}"""
    prompt = f"{Colors.GREEN}(NovelStudio) > {Colors.ENDC}"

    def __init__(self):
        super().__init__()
        load_dotenv()
        
        print_c("正在初始化核心组件...", Colors.CYAN)
        self.memory = MemoryManager()
        self.context_mgr = ContextManager(self.memory)
        
        # 懒加载 Agents
        self._editor = None
        self._writer = None
        self._reviewer = None
        self._archivist = None
        
        self.current_chapter = self._get_next_chapter_num()

    # --- Agent Properties (Lazy Load) ---
    @property
    def editor(self):
        if not self._editor: self._editor = EditorAgent()
        return self._editor
    
    @property
    def writer(self):
        if not self._writer: self._writer = WriterAgent()
        return self._writer
    
    @property
    def reviewer(self):
        if not self._reviewer: self._reviewer = ReviewerAgent(self.memory)
        return self._reviewer
    
    @property
    def archivist(self):
        if not self._archivist: self._archivist = ArchivistAgent(self.memory)
        return self._archivist

    # --- Helper Methods ---
    def _get_next_chapter_num(self) -> int:
        """获取下一个章节号（目前简单基于数据库统计）"""
        # 这里需要从 memory 获取，暂时通过查询 sqlite 实现
        # 为了简单，我们先总是从 memory 状态里读，或者假设用户知道
        # 更好的做法是在 memory 加个 get_max_chapter_num 接口
        # 现阶段先返回 1，除非数据库里有记录
        conn = self.memory.get_narrative_focus()
        # 遗憾的是 focus 表没存最大章节号。
        # 我们可以查 chapters 表
        import sqlite3
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(chapter_num) FROM chapters")
        row = cursor.fetchone()
        conn.close()
        return (row[0] or 0) + 1

    # --- Commands ---

    def do_status(self, arg):
        """显示当前世界观状态与进度"""
        focus = self.memory.get_narrative_focus()
        print_c(f"\n📊 当前状态 (Next: Chapter {self.current_chapter})", Colors.HEADER)
        print(f"  - 卷名: {focus['volume']}")
        print(f"  - 单元: {focus['arc']}")
        print(f"  - 节拍: {focus['beat']} (本拍已持续 {focus['chapters_since_last_beat']} 章)")
        print(f"  - 目标: {focus['goal']}")
        print(f"  - 冲突: {focus['conflict']}")
        print(f"  - 日期: {focus.get('date', '未知')}")
        print("")

    def do_init(self, arg):
        """初始化世界观 (慎用，会重置 narrtive_focus)"""
        if input(f"{Colors.WARNING}⚠️ 确定要重置世界观状态吗？(y/n): {Colors.ENDC}").lower() != 'y':
            return
        
        volume = input("当前卷名 (e.g. 第一卷 风起云涌): ")
        arc = input("当前单元 (e.g. 入门篇): ")
        beat = input("当前节拍 (e.g. 铺垫): ")
        goal = input("当前目标 (e.g. 主角加入宗门): ")
        conflict = input("核心冲突 (e.g. 资质太差): ")
        state = input("世界局势 (e.g. 相对和平): ")
        date = input("起始日期 (e.g. 天道历元年1月1日): ")
        
        self.memory.update_narrative_focus(volume, arc, beat, goal, conflict, state, reset_beat=True, current_date=date)
        print_c("✅ 世界观初始化完成。", Colors.GREEN)

    def do_write(self, arg):
        """开始创作流程: write [chapter_num]"""
        try:
            chap_num = int(arg) if arg else self.current_chapter
        except ValueError:
            print_c("❌ 请输入有效的章节数字。", Colors.FAIL)
            return

        self._run_workflow(chap_num)
        self.current_chapter = chap_num + 1

    def do_auto(self, arg):
        """自动连续创作: auto <count>"""
        try:
            count = int(arg)
        except ValueError:
            print_c("❌ 请输入要生成的章节数量。", Colors.FAIL)
            return

        start_chap = self.current_chapter
        for i in range(count):
            current = start_chap + i
            print_c(f"\n🚀 [Auto Mode] 正在启动第 {current} 章 ({i+1}/{count})...", Colors.HEADER)
            try:
                self._run_workflow(current, auto_approve=True)
            except Exception as e:
                print_c(f"❌ 自动模式中断: {e}", Colors.FAIL)
                break
        self.current_chapter = start_chap + count

    def do_exit(self, arg):
        """退出程序"""
        print("Goodbye!")
        return True

    # --- Workflow Logic ---

    def _run_workflow(self, chap_num: int, auto_approve: bool = False):
        start_time = time.time()
        print_c(f"\n🎬 === 开始创作 第 {chap_num} 章 ===\n", Colors.BOLD)

        # 1. 上下文组装
        print_c("Step 1: 组装上下文 (Context Assembly)", Colors.CYAN)
        prev_summary = self.memory.get_chapter_summary(chap_num - 1)
        editor_ctx = self.context_mgr.build_editor_context(chap_num, prev_summary)
        
        # 2. 生成大纲 (Editor)
        print_c("Step 2: 主编构思大纲 (Editor Agent)", Colors.CYAN)
        outline_data = self.editor.generate_outline(editor_ctx, chap_num)
        
        # 显示大纲预览
        print(f"\n📜 [大纲预览] {outline_data.get('title', '无标题')}")
        print(f"   叙事重心: {outline_data.get('narrative_focus', '未知')}")
        outline_list = outline_data.get('outline', [])
        if isinstance(outline_list, list):
            for line in outline_list:
                print(f"   - {line}")
        else:
            print(f"   {outline_list[:200]}...")

        # 人工审核 (除非自动模式)
        if not auto_approve:
            choice = input(f"\n{Colors.WARNING}按 Enter 继续生成正文，输入 'n' 重新生成大纲，输入 'q' 退出: {Colors.ENDC}")
            if choice.lower() == 'q': return
            if choice.lower() == 'n': 
                print_c("🔄 重新生成大纲...", Colors.WARNING)
                return self._run_workflow(chap_num, auto_approve) # 递归重试
        
        # 3. 撰写正文 (Writer)
        print_c("\nStep 3: 作家撰写正文 (Writer Agent)", Colors.CYAN)
        # 组装 Writer 需要的详细上下文 (含 RAG, 图谱, 地理围栏)
        active_chars = outline_data.get("active_characters", [])
        scene_loc = outline_data.get("scene_location", "未知")
        atmosphere = outline_data.get("atmosphere", None) # 获取氛围设定
        
        # 无论 outline 是 list 还是 str，都转成 str 给 writer
        outline_str = "\n".join(outline_list) if isinstance(outline_list, list) else str(outline_list)
        
        writer_ctx = self.context_mgr.build_writer_context(
            chapter_num=chap_num, 
            outline=outline_str, 
            active_characters=active_chars,
            scene_location=scene_loc,
            atmosphere=atmosphere
        )
        
        content = self.writer.write_chapter(outline_str, writer_ctx)
        word_count = len(content)
        print_c(f"✅ 正文生成完毕 (约 {word_count} 字)", Colors.GREEN)
        
        # 4. 审核 (Reviewer)
        print_c("\nStep 4: 书评人审核 (Reviewer Agent)", Colors.CYAN)
        review_result = self.reviewer.review_draft(content, chapter_num=chap_num)
        
        if "PASS" in review_result:
            print_c("✅ 审核通过！", Colors.GREEN)
        else:
            print_c(f"⚠️ 审核意见:\n{review_result}", Colors.WARNING)
            if not auto_approve:
                if input("是否强制归档？(y/n): ").lower() != 'y':
                    print_c("❌ 创作终止，未归档。", Colors.FAIL)
                    return

        # 5. 归档 (Archivist)
        print_c("\nStep 5: 档案员归档 (Archivist Agent)", Colors.CYAN)
        # 自动重试机制已在 Agent 内部实现
        self.archivist.archive_chapter(content, chap_num)
        
        elapsed = time.time() - start_time
        print_c(f"\n🎉 第 {chap_num} 章创作完成！耗时 {elapsed:.2f}s", Colors.GREEN)

if __name__ == "__main__":
    try:
        app = NovelStudioShell()
        app.cmdloop()
    except KeyboardInterrupt:
        print("\nOperation cancelled.")