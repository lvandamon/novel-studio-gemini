import tiktoken
from typing import List, Dict, Any, Optional
from core.memory import MemoryManager
from core.physics import PhysicalityEngine
import json
from langchain_core.output_parsers import StrOutputParser
from core.llm import get_deepseek_chat
from core.prompts import CONTEXT_INTENT_PROMPT, CONTEXT_COMPRESSION_PROMPT
import re

class ContextManager:
    """
    分层级上下文管理器 (Hierarchical Context Manager)
    
    层级结构：
    1. Global Layer (世界层): 终极目标、世界规则、当前卷/单元规划。 (Cacheable)
    2. Local Layer (场景层): 当前场景位置、在场角色(Roster)、上一章摘要。 (Dynamic)
    3. Retrieval Layer (检索层): 针对当前情节大纲(Outline)动态检索的事件、伏笔、图谱。 (Highly Dynamic)
    
    Token 预算策略:
    - 优先保住 Global 和 Local (基础连贯性)。
    - 剩余预算大量分配给 Retrieval (细节丰富度)。
    """
    
    def __init__(self, memory_manager: MemoryManager, model_name: str = "gpt-4o"):
        self.memory = memory_manager
        self.physics_engine = PhysicalityEngine(self.memory)
        try:
            self.encoder = tiktoken.encoding_for_model(model_name)
        except:
            self.encoder = tiktoken.get_encoding("cl100k_base")

        # 🔥 P1升级: 动态预算系统 (适配200万字长篇后期需求)
        # 根据章节数动态调整预算上限
        self.base_total_budget = 64000  # 基础预算
        self.max_total_budget = 96000   # 最大预算 (用于后期复杂场景)
        self.total_budget = self.base_total_budget  # 当前预算(动态调整)

        # 基础层预算 (硬性保留) - 同步扩容
        self.base_budgets = {
            "global": 6000,  # 扩容50%
            "local_roster": 4000,
            "prev_summary": 3000,
            "vocabulary": 1500,
        }

        # 🆕 层级缓存系统 (Hierarchical Cache)
        # 用于缓存不常变化的全局内容 (世界圣经、卷级规划)
        self._cache = {
            "world_bible": {"content": None, "chapter": -1},  # 每10章刷新
            "volume_plan": {"content": None, "volume_id": None},  # 卷切换时刷新
            "vocabulary": {"content": None, "arc_name": None},  # 单元切换时刷新
            "character_summaries": {}  # 🔥 P1新增: 角色摘要缓存
        }

        # 🔥 P1新增: 压缩策略配置
        self.compression_config = {
            "aggressive_threshold": 0.8,  # 超过80%预算启动激进压缩
            "chunk_size": 8000,  # 分块压缩大小
            "max_compression_rounds": 3  # 最大压缩轮次
        }

        # 🔥 P3新增: 关键信息保护标记 (Critical Information Markers)
        # 这些标记包裹的内容在压缩时必须优先保留
        self.critical_markers = {
            "anchors": ("⚓️", "⚓️END"),       # 黄金锚点
            "physics": ("⚙️", "⚙️END"),        # 物理约束
            "core_hook": ("‼️", "‼️END"),      # 核心伏笔
            "severed": ("🚨", "🚨END"),        # 断肢警报
            "director": ("🎬", "🎬END"),       # 导演指令
        }

        # 🔥 P3新增: 关键词保护列表 (压缩时必须保留的关键词)
        self.protected_keywords = [
            "黄金锚点", "绝对不可违背", "部位警报", "缺失", "残废", "SEVERED", "CRIPPLED",
            "核心悬念", "导演指令", "物理法则", "必须严格遵守"
        ]

        # 初始化 LLM 链
        self.llm = get_deepseek_chat(temperature=0.1)
        self.intent_chain = CONTEXT_INTENT_PROMPT | self.llm | StrOutputParser()
        self.compressor_chain = CONTEXT_COMPRESSION_PROMPT | self.llm | StrOutputParser()

    def _adjust_budget_for_chapter(self, chapter_num: int, active_characters_count: int = 0,
                                     historical_usage: int = None):
        """
        🔥 P1新增 + P4升级: 根据章节数和场景复杂度动态调整预算

        策略:
        - 前100章: 基础预算 (64k)
        - 100-500章: 线性增长到 80k
        - 500章+: 最大预算 (96k)
        - 多角色场景 (>7人): 额外 +10%
        - 🔥 P4新增: 基于历史真实Token使用量自适应调整
        """
        base = self.base_total_budget

        if chapter_num < 100:
            self.total_budget = base
        elif chapter_num < 500:
            # 线性插值
            progress = (chapter_num - 100) / 400
            self.total_budget = int(base + (self.max_total_budget - base) * 0.5 * progress)
        else:
            self.total_budget = int(base + (self.max_total_budget - base) * 0.5)

        # 多角色加成
        if active_characters_count > 7:
            self.total_budget = int(self.total_budget * 1.1)

        # 🔥 P4新增: 基于历史使用量的自适应调整
        if historical_usage is not None and historical_usage > 0:
            # 如果历史使用量接近或超过当前预算,自动扩容
            usage_ratio = historical_usage / self.total_budget
            if usage_ratio > 0.9:
                # 使用量超过90%,扩容20%
                self.total_budget = int(self.total_budget * 1.2)
                print(f"   📈 Context预算自适应扩容: {usage_ratio:.1%} -> +20%")
            elif usage_ratio > 0.8:
                # 使用量超过80%,扩容10%
                self.total_budget = int(self.total_budget * 1.1)

        # 上限保护
        self.total_budget = min(self.total_budget, self.max_total_budget)

    def get_real_token_usage(self, content: str) -> Dict[str, int]:
        """
        🔥 P4新增: 获取真实Token使用统计

        Returns:
            Dict with 'total', 'global', 'local', 'retrieval' token counts
        """
        return {
            "total": self._count_tokens(content),
            "budget": self.total_budget,
            "usage_rate": round(self._count_tokens(content) / max(1, self.total_budget), 3)
        }

    def estimate_context_complexity(self, chapter_num: int, active_characters: List[str],
                                     outline: str) -> Dict[str, Any]:
        """
        🔥 P4新增: 预估上下文复杂度

        用于在生成前预判是否需要调整预算

        Returns:
            Dict with complexity metrics and recommendations
        """
        complexity = {
            "character_count": len(active_characters),
            "outline_tokens": self._count_tokens(outline),
            "estimated_base": 0,
            "risk_level": "LOW",
            "recommendations": []
        }

        # 基础估算
        base_estimate = 5000  # 世界圣经 + 基础状态
        per_character = 1500  # 每角色预估
        outline_multiplier = 3  # 大纲衍生内容倍数

        complexity["estimated_base"] = (
            base_estimate +
            len(active_characters) * per_character +
            complexity["outline_tokens"] * outline_multiplier
        )

        # 风险评估
        usage_rate = complexity["estimated_base"] / self.total_budget

        if usage_rate > 0.9:
            complexity["risk_level"] = "HIGH"
            complexity["recommendations"].append("建议减少活跃角色数量或简化大纲")
        elif usage_rate > 0.7:
            complexity["risk_level"] = "MEDIUM"
            complexity["recommendations"].append("可能需要启用压缩策略")
        else:
            complexity["risk_level"] = "LOW"

        if len(active_characters) > 10:
            complexity["recommendations"].append("建议启用角色限流分批处理")

        return complexity

    def _count_tokens(self, text: str) -> int:
        return len(self.encoder.encode(text))

    def _trim_lines_to_budget(self, text: str, budget: int, from_start: bool = True) -> str:
        """按行裁剪文本以适应 token 预算 (Physical Fallback)"""
        if not text: return ""
        lines = text.split('\n')
        result = []
        current_tokens = 0
        
        iterator = lines if from_start else reversed(lines)
        
        for line in iterator:
            t = self._count_tokens(line)
            if current_tokens + t > budget:
                break
            result.append(line)
            current_tokens += t
            
        if not from_start:
            result.reverse()
            
        return "\n".join(result)

    def _extract_critical_sections(self, content: str) -> tuple:
        """
        🔥 P3新增: 提取关键信息段落

        返回: (critical_content, remaining_content, critical_tokens)
        关键内容在压缩时会被保护
        """
        critical_parts = []
        remaining = content

        # 1. 提取标记保护的内容
        for marker_name, (start_marker, end_marker) in self.critical_markers.items():
            pattern = f"{re.escape(start_marker)}(.*?){re.escape(end_marker)}"
            matches = re.findall(pattern, content, re.DOTALL)
            for match in matches:
                critical_parts.append(f"{start_marker}{match}{end_marker}")

        # 2. 提取包含保护关键词的行
        lines = content.split('\n')
        protected_lines = []
        for line in lines:
            if any(kw in line for kw in self.protected_keywords):
                if line not in protected_lines:
                    protected_lines.append(line)

        # 组装关键内容
        critical_content = '\n'.join(critical_parts + protected_lines)
        critical_tokens = self._count_tokens(critical_content)

        # 从原内容中移除已保护的内容(避免重复)
        for part in critical_parts:
            remaining = remaining.replace(part, '')

        for line in protected_lines:
            if line in remaining:
                remaining = remaining.replace(line + '\n', '')

        return critical_content, remaining, critical_tokens

    def _smart_fit(self, content: str, budget: int) -> str:
        """
        🔥 P1升级 + P3修复: 分块递进压缩策略 + 关键信息保护

        策略:
        1. 提取关键信息(锚点/物理约束/核心伏笔)单独保护
        2. 计算剩余预算给可压缩内容
        3. 轻度超标 (<1.5x): 单次语义压缩
        4. 中度超标 (1.5x-3x): 分块压缩后合并
        5. 严重超标 (>3x): 多轮激进压缩
        6. 最终兜底: 物理裁剪
        7. 重新组装: 关键信息 + 压缩后内容
        """
        current_usage = self._count_tokens(content)
        if current_usage <= budget:
            return content

        overflow_ratio = current_usage / budget
        print(f"   🤏 Context Overflow ({current_usage} > {budget}, ratio: {overflow_ratio:.2f}x). Triggering Smart Compression...")

        # 🔥 P3新增: 提取关键信息
        critical_content, remaining_content, critical_tokens = self._extract_critical_sections(content)

        if critical_tokens > 0:
            print(f"   🛡️ 已保护 {critical_tokens} tokens 的关键信息")

        # 计算可压缩内容的预算
        compressible_budget = budget - critical_tokens

        # 如果关键信息本身就超出预算，只能物理裁剪关键信息
        if compressible_budget <= 0:
            print(f"   ⚠️ 关键信息({critical_tokens} tokens)超出总预算({budget})，强制裁剪...")
            return self._trim_lines_to_budget(critical_content, budget)

        remaining_usage = self._count_tokens(remaining_content)
        if remaining_usage <= compressible_budget:
            # 不需要压缩
            return critical_content + '\n' + remaining_content

        # 计算需要压缩的比例
        remaining_overflow = remaining_usage / compressible_budget

        try:
            if remaining_overflow <= 1.5:
                compressed = self._single_compress(remaining_content, compressible_budget)
            elif remaining_overflow <= 3.0:
                compressed = self._chunked_compress(remaining_content, compressible_budget)
            else:
                compressed = self._aggressive_compress(remaining_content, compressible_budget)

            # 🔥 P3新增: 重新组装(关键信息在前)
            if critical_content.strip():
                return critical_content + '\n\n' + compressed
            return compressed

        except Exception as e:
            print(f"   ⚠️ Compression Failed: {e}. Fallback to trim.")
            trimmed = self._trim_lines_to_budget(remaining_content, compressible_budget)
            if critical_content.strip():
                return critical_content + '\n\n' + trimmed
            return trimmed

    def _single_compress(self, content: str, budget: int) -> str:
        """单次语义压缩"""
        compressed = self.compressor_chain.invoke({
            "content": content,
            "budget": budget
        })

        new_usage = self._count_tokens(compressed)
        print(f"   -> Single compressed to {new_usage} tokens.")

        if new_usage > budget:
            return self._trim_lines_to_budget(compressed, budget)
        return compressed

    def _chunked_compress(self, content: str, budget: int) -> str:
        """
        🔥 P1新增: 分块压缩

        将内容按段落分块，每块独立压缩后合并
        """
        chunk_size = self.compression_config["chunk_size"]

        # 按段落分割
        paragraphs = content.split('\n\n')
        chunks = []
        current_chunk = []
        current_size = 0

        for para in paragraphs:
            para_size = self._count_tokens(para)
            if current_size + para_size > chunk_size and current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = [para]
                current_size = para_size
            else:
                current_chunk.append(para)
                current_size += para_size

        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))

        print(f"   -> Split into {len(chunks)} chunks for parallel compression")

        # 每块分配预算
        per_chunk_budget = budget // len(chunks)
        compressed_chunks = []

        for i, chunk in enumerate(chunks):
            chunk_tokens = self._count_tokens(chunk)
            if chunk_tokens > per_chunk_budget:
                compressed = self.compressor_chain.invoke({
                    "content": chunk,
                    "budget": per_chunk_budget
                })
                compressed_chunks.append(compressed)
            else:
                compressed_chunks.append(chunk)

        result = '\n\n'.join(compressed_chunks)
        final_usage = self._count_tokens(result)
        print(f"   -> Chunked compression complete: {final_usage} tokens")

        if final_usage > budget:
            return self._trim_lines_to_budget(result, budget)
        return result

    def _aggressive_compress(self, content: str, budget: int) -> str:
        """
        🔥 P1新增: 多轮激进压缩

        用于严重超标情况，迭代压缩直到满足预算
        """
        max_rounds = self.compression_config["max_compression_rounds"]
        current_content = content
        current_usage = self._count_tokens(content)

        for round_num in range(max_rounds):
            target_budget = budget if round_num == max_rounds - 1 else int(current_usage * 0.5)
            target_budget = max(target_budget, budget)

            print(f"   -> Aggressive round {round_num + 1}/{max_rounds}, target: {target_budget}")

            compressed = self.compressor_chain.invoke({
                "content": current_content,
                "budget": target_budget
            })

            new_usage = self._count_tokens(compressed)
            print(f"   -> Round {round_num + 1} result: {new_usage} tokens")

            if new_usage <= budget:
                return compressed

            current_content = compressed
            current_usage = new_usage

        # 最终兜底
        print("   ⚠️ Max rounds reached. Applying physical trim.")
        return self._trim_lines_to_budget(current_content, budget)

    def _get_cached_or_build(self, cache_key: str, build_func, invalidate_check) -> str:
        """
        🆕 缓存辅助函数: 检查缓存是否有效,无效则重建

        Args:
            cache_key: 缓存键名
            build_func: 无参构建函数
            invalidate_check: 返回是否失效的函数
        """
        cache_entry = self._cache.get(cache_key)
        if cache_entry and cache_entry["content"] is not None and not invalidate_check(cache_entry):
            return cache_entry["content"]

        # 缓存失效,重建
        content = build_func()
        self._cache[cache_key]["content"] = content
        return content

    def _build_vocabulary_constraints(self, volume_name: str, arc_name: str) -> str:
        """
        构建动态词表约束 (Dynamic Vocabulary Constraints)。
        🔥 P0修复: 使用缓存减少重复检索
        """
        def build():
            # 检索 Terminology 相关的圣经条目
            vocab_context = self.memory.get_bible_context(query=f"{volume_name} {arc_name} 术语 词汇 禁忌语")

            # 基础通用约束 (Hardcoded Baseline)
            baseline = """
### 🚫 词汇禁区 (Vocabulary Taboos)
- 严禁出现现代科技词汇 (如: 信号, 逻辑, 降维打击, 量子, 甚至"思考方式"等现代口语)。
- 严禁出现 OOC 网络热词。
- 严禁出现非本世界观的计量单位 (除非圣经另有规定)。

### ✅ 推荐词汇 (Recommended Lexicon)
- 使用古雅、稳重的半文言或正统网文仙侠笔触。
- 动作描写优先使用具体的武学方位和劲力描述。
"""
            if vocab_context:
                return f"{baseline}\n### 🌍 当前阶段特定词表:\n{vocab_context}"
            return baseline

        def check_invalid(entry):
            return entry.get("arc_name") != arc_name

        result = self._get_cached_or_build("vocabulary", build, check_invalid)
        self._cache["vocabulary"]["arc_name"] = arc_name
        return result

    def build_director_context(self, chapter_num: int) -> str:
        """
        为 Director (导演) 提供的宏观视角上下文。
        不需要太多细节，需要的是 结构(Structure) 和 状态(State)。
        """
        focus = self.memory.get_narrative_focus()
        active_plan = self.memory.get_active_plan()
        
        # 0. 获取世界圣经 (相关核心设定)
        bible_text = self.memory.get_bible_context(query=focus['goal'])

        # 1. 进度概览
        progress_text = f"当前进度: 第 {chapter_num} 章\n"
        if active_plan["volume"]:
            progress_text += f"卷: {active_plan['volume']['name']} (目标: {active_plan['volume']['goal']})\n"
        if active_plan["arc"]:
            progress_text += f"单元: {active_plan['arc']['name']} (目标: {active_plan['arc']['goal']})\n"
            progress_text += f"单元关键节点: {json.dumps(active_plan['arc']['key_events'], ensure_ascii=False)}\n"
            
        # 2. 叙事焦点状态
        focus_text = f"""
当前节拍: {focus['beat']} (已持续 {focus.get('chapters_since_last_beat', 0)} 章)
当前冲突: {focus['conflict']}
世界状态摘要: {focus['state']}
"""

        # 🔥 P2新增: 导演指令注入
        pacing = focus.get('pacing', 'Normal')
        director_order = f"## 0. 导演最高指令 (Director's Order)\n【节奏要求】: {pacing}"
        if pacing != 'Normal':
            director_order += " (请在大纲规划中严格体现此节奏)"

        # 3. 近期摘要 (最近 10 章，比 Writer 看得远)
        summaries = []
        for i in range(max(1, chapter_num - 10), chapter_num):
            s = self.memory.get_chapter_summary(i)
            summaries.append(f"Ch{i}: {s}")
        recent_history = "\n".join(summaries)
        
        # 4. 活跃伏笔 (导演需要检查哪些该回收了)
        hooks = self.memory.get_active_foreshadowing()
        hooks_text = "\n".join([f"- [ID:{h['id']}] (Ch{h['chapter']}) {h['content']}" for h in hooks]) if hooks else "无活跃伏笔"

        return f"""
{bible_text}

# 🎬 导演控制台
{director_order}

## 1. 宏观进度
{progress_text}

## 2. 叙事状态
{focus_text}

## 3. 待处理伏笔/悬念
{hooks_text}

## 4. 近期剧情流 (Last 10 Chapters)
{recent_history}
"""

    def _rank_characters_by_priority(self, characters: List[str], chapter_num: int, outline: str) -> List[str]:
        """
        🔥 P1新增: 角色优先级评估算法

        评分维度:
        1. 大纲提及次数 (30%)
        2. 重要性等级 (25%)
        3. 近期活跃度 (25%)
        4. 主角标记 (20%)

        Returns:
            按优先级降序排列的角色列表
        """
        scores = {}

        for char_name in characters:
            score = 0.0

            # 1. 大纲提及次数 (强相关性)
            mentions = outline.count(char_name)
            score += min(mentions * 10, 30)  # 上限30分

            # 2. 重要性等级
            char = self.memory.get_character(char_name)
            if char:
                importance = char.get('importance', 5)  # 1-10
                score += (importance / 10) * 25

                # 3. 近期活跃度 (最近10章出现次数)
                recent_chapters = max(1, chapter_num - 10)
                # 简化: 查询近期事件
                conn = self.memory._get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM events
                    WHERE character_name = ? AND chapter_num >= ?
                ''', (char_name, recent_chapters))
                recent_events = cursor.fetchone()[0]
                conn.close()
                score += min(recent_events * 2.5, 25)

                # 4. 主角标记
                if char.get('is_protagonist', False):
                    score += 20

            scores[char_name] = score

        # 按分数降序排序
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return [name for name, _ in ranked]

    def apply_character_rate_limiting(self, characters: List[str], chapter_num: int, outline: str,
                                      max_primary: int = 5, max_total: int = 10) -> Dict[str, List[str]]:
        """
        🔥 P2新增: 多角色场景限流器

        当角色数量超过阈值时，自动分组处理:
        - Primary组: 获得完整的上下文 (最多max_primary人)
        - Secondary组: 获得简化的上下文 (总数不超过max_total)
        - Excluded组: 被排除的角色 (超出max_total)

        策略:
        - 超过10人: 发出警告，分批处理
        - 超过15人: 强制限制，可能需要分段生成

        Returns:
            Dict with 'primary', 'secondary', 'excluded' lists
        """
        total_count = len(characters)

        result = {
            "primary": [],
            "secondary": [],
            "excluded": [],
            "warning": None,
            "requires_batch_generation": False
        }

        if total_count <= max_primary:
            # 角色数量较少，全部作为主要角色
            result["primary"] = characters
            return result

        # 角色排序
        ranked = self._rank_characters_by_priority(characters, chapter_num, outline)

        if total_count <= max_total:
            # 中等数量: 分为主要和次要
            result["primary"] = ranked[:max_primary]
            result["secondary"] = ranked[max_primary:]
            print(f"   👥 角色限流: {total_count}人 -> 主要{len(result['primary'])}人 + 次要{len(result['secondary'])}人")
            return result

        # 大量角色: 需要排除部分
        result["primary"] = ranked[:max_primary]
        result["secondary"] = ranked[max_primary:max_total]
        result["excluded"] = ranked[max_total:]

        # 发出警告
        if total_count > 15:
            result["warning"] = f"⚠️ 场景角色过多({total_count}人)，建议分段生成以保证质量"
            result["requires_batch_generation"] = True
            print(f"   ⚠️ 角色限流警告: {total_count}人超出上限，排除{len(result['excluded'])}人")
        else:
            print(f"   👥 角色限流: {total_count}人 -> 主要{max_primary}人 + 次要{max_total - max_primary}人，排除{len(result['excluded'])}人")

        return result

    def build_batch_context_for_crowd_scene(self, chapter_num: int, outline: str,
                                            all_characters: List[str], scene_location: str,
                                            batch_size: int = 8) -> List[Dict[str, Any]]:
        """
        🔥 P2新增: 大规模场景分批上下文生成

        用于超过15人的大场景，将场景分成多个批次处理:
        - 每批次最多batch_size个角色
        - 主角始终在每个批次中
        - 返回多个上下文包，供Writer分段生成

        Returns:
            List of context dicts, each containing:
            - batch_num: 批次号
            - characters: 本批次角色
            - context: 本批次上下文
            - focus_hint: 本批次写作重点提示
        """
        # 获取主角
        protagonists = []
        for char_name in all_characters:
            char = self.memory.get_character(char_name)
            if char and char.get('is_protagonist', False):
                protagonists.append(char_name)

        # 如果没有标记主角，取大纲中提及最多的
        if not protagonists:
            mention_counts = [(c, outline.count(c)) for c in all_characters]
            mention_counts.sort(key=lambda x: -x[1])
            if mention_counts:
                protagonists = [mention_counts[0][0]]

        # 排除主角后的其他角色
        others = [c for c in all_characters if c not in protagonists]
        ranked_others = self._rank_characters_by_priority(others, chapter_num, outline)

        # 分批
        batches = []
        batch_num = 0

        for i in range(0, len(ranked_others), batch_size - len(protagonists)):
            batch_chars = protagonists + ranked_others[i:i + batch_size - len(protagonists)]
            batch_num += 1

            # 为每个批次构建简化上下文
            batch_context = {
                "batch_num": batch_num,
                "total_batches": (len(ranked_others) + batch_size - len(protagonists) - 1) // (batch_size - len(protagonists)) + 1,
                "characters": batch_chars,
                "focus_hint": f"本批次重点描写: {', '.join(batch_chars[:3])}",
                "context": None  # 延迟构建
            }

            batches.append(batch_context)

        print(f"   📦 大场景分批: {len(all_characters)}人 -> {len(batches)}个批次")
        return batches

    def _analyze_plot_intent(self, outline: str) -> Dict[str, Any]:
        """
        [核心逻辑升级] AI 意图解析器
        使用 DeepSeek-V3 快速分析情节意图，返回结构化检索指令。
        """
        print("   🧠 正在解析本章叙事意图...")
        try:
            response = self.intent_chain.invoke({"outline": outline})
            
            # 清理可能的 markdown 包裹
            clean_json = response.strip()
            if "```json" in clean_json:
                clean_json = re.search(r'```json\s*(\{.*\})\s*```', clean_json, re.DOTALL).group(1)
            elif "```" in clean_json:
                clean_json = clean_json.replace("```", "")
                
            intent_data = json.loads(clean_json)
            # 简单的验证，确保字段存在
            required_fields = ["type", "needs_skills", "needs_relations", "needs_history", "needs_hooks", "needs_world_rules"]
            for field in required_fields:
                if field not in intent_data:
                    intent_data[field] = False # Default fallback
            
            print(f"   👉 意图识别: [{intent_data.get('type')}] - 需要技能:{intent_data.get('needs_skills')} | 需要关系:{intent_data.get('needs_relations')}")
            return intent_data
            
        except Exception as e:
            print(f"   ⚠️ 意图解析失败，回退到基础模式: {e}")
            # Fallback heuristic
            intent = {
                "type": "General",
                "needs_skills": False,
                "needs_relations": False,
                "needs_history": False,
                "needs_hooks": False,
                "needs_world_rules": False
            }
            low_outline = outline.lower()
            if any(w in low_outline for w in ["打", "战", "杀", "斗", "招式", "伤"]):
                intent["type"] = "Combat"
                intent["needs_skills"] = True
            elif any(w in low_outline for w in ["说", "谈", "骂", "争执", "秘密", "心想"]):
                intent["type"] = "Social"
                intent["needs_relations"] = True
                
            return intent

    def build_writer_context(self, chapter_num: int, outline: str, active_characters: List[str], scene_location: str, atmosphere: Dict[str, str] = None) -> str:
        """
        重构后的 Writer 上下文构建：意图驱动型检索 + 智能压缩
        """
        # 0. 意图分析
        intent = self._analyze_plot_intent(outline)
        
        # --- 1. World Bible (绝对真理层 - 不可压缩) ---
        bible_query = f"{scene_location}"
        if intent.get('needs_world_rules') or intent.get('needs_skills'):
             bible_query += f" {outline[:100]} 功法 境界 规则"
        else:
             bible_query += f" {outline[:50]}"
             
        bible_text = self.memory.get_bible_context(query=bible_query, active_entities=active_characters)
        
        # --- 1.5. Physicality Engine (物理法则层 - 不可压缩) ---
        physics_text = self.physics_engine.get_hard_constraints_for_prompt(active_characters, scene_location)
        
        current_budget = self.total_budget - self._count_tokens(bible_text) - self._count_tokens(physics_text)

        # --- 2. Story State (状态层 - 必须保留，但可轻度压缩) ---
        focus = self.memory.get_narrative_focus()
        active_plan = self.memory.get_active_plan()
        prev_summary = self.memory.get_chapter_summary(chapter_num - 1)
        
        vocab_text = self._build_vocabulary_constraints(
            active_plan.get('volume', {}).get('name', '默认'),
            active_plan.get('arc', {}).get('name', '默认')
        )

        active_hooks = ""
        # 强制获取所有伏笔，进行分级筛选
        all_hooks = self.memory.get_active_foreshadowing()
        
        mandatory_hooks = []
        contextual_hooks = []
        
        for h in all_hooks:
            # Importance >= 8: 核心伏笔，必须时刻提醒 (The "Sword of Damocles")
            if h.get('importance', 5) >= 8:
                mandatory_hooks.append(h)
            # 否则，如果是侦探意图或 Intent 明确需要，加入上下文候选
            elif intent["needs_hooks"] or intent["type"] == "Investigation":
                contextual_hooks.append(h)
                
        # 组装文本
        hook_lines = []
        if mandatory_hooks:
            hook_lines.append("‼️【核心悬念 (Core Mysteries) - 必须铭记】")
            for h in mandatory_hooks:
                hook_lines.append(f"- [ID:{h['id']}] {h['content']} (Imp:{h.get('importance')})")
        
        if contextual_hooks:
            hook_lines.append("🔍【线索提示 (Clues)】")
            for h in contextual_hooks:
                hook_lines.append(f"- [ID:{h['id']}] {h['content']}")
                
        if hook_lines:
            active_hooks = "\n" + "\n".join(hook_lines)

        state_text = f"""
# 🌍 宏观状态
【目标】: {focus['goal']}
【当前冲突】: {focus['conflict']}
【卷/单元规划】: {active_plan.get('volume', {}).get('name', '默认')} -> {active_plan.get('arc', {}).get('name', '默认')}
{active_hooks}

# 📜 前情提要
【上一章回顾】: {prev_summary}
"""

        # 🔥 P2新增: 导演节奏指令
        pacing = focus.get('pacing', 'Normal')
        director_instruction = f"""
# 🎬 导演指令 (Director's Cut)
【当前节奏指令】: {pacing}
"""
        if pacing in ["Accelerate", "Fast", "High Tension"]:
             director_instruction += "【执行要求】: 减少环境描写和心理独白，使用短句，加快叙事速度，聚焦动作与冲突。\n"
        elif pacing in ["Decelerate", "Slow", "Build-up"]:
             director_instruction += "【执行要求】: 增加环境渲染和心理细节，放慢节奏，营造氛围或情感张力。\n"
        elif pacing in ["Climax", "Peak"]:
             director_instruction += "【执行要求】: 全力渲染高潮！将所有情绪和冲突推向顶点，不惜笔墨描写震撼场景。\n"
        
        # 计算剩余预算
        used_tokens = self._count_tokens(state_text) + self._count_tokens(vocab_text) + self._count_tokens(director_instruction)
        retrieval_budget = current_budget - used_tokens
        # 确保至少有 2000 tokens 给检索，否则报错或强行分配
        if retrieval_budget < 2000:
             retrieval_budget = 2000 

        # --- 3. Targeted Retrieval (定向检索层 - 智能压缩区) ---
        
        # A. 角色状态 - 🔥 P1优化: 动态优先级分配
        # 当角色数量>5时,按重要性+活跃度排序,只保留Top5详情
        char_info = "# 👥 角色实时状态\n"

        # 🔥 P1新增: 角色优先级评估
        if len(active_characters) > 5:
            print(f"   ⚠️ 角色数过多({len(active_characters)}), 启动优先级筛选...")
            ranked_chars = self._rank_characters_by_priority(active_characters, chapter_num, outline)
            primary_chars = ranked_chars[:5]  # Top5详情
            secondary_chars = ranked_chars[5:]  # 其他简化
        else:
            primary_chars = active_characters
            secondary_chars = []

        # 主要角色: 完整信息
        for char_name in primary_chars:
            # 先插入锚点
            anchors = self.memory.get_character_anchors(char_name)
            if anchors:
                char_info += f"## {char_name} - 黄金锚点 (绝对不可违背)\n{anchors}\n\n"

            details = self.memory.get_character_details([char_name], query=outline)
            char_info += f"## {char_name} - 当前状态\n{details}\n"

        # 次要角色: 一句话摘要
        if secondary_chars:
            char_info += "\n## 其他在场角色 (简要)\n"
            for char_name in secondary_chars:
                char = self.memory.get_character(char_name)
                if char:
                    level = char.get('level', '未知')
                    trait = char.get('personality_trait', '').split(',')[0] if char.get('personality_trait') else '普通'
                    char_info += f"- **{char_name}** [{level}] - {trait}\n"
        
        # B. 关系深度检索 (Subgraph Extraction) - 🔥 P0优化: 传递章节参数
        graph_info = ""
        if intent["needs_relations"] or intent["type"] == "Social" or len(active_characters) > 1:
            graph_info = self.memory.graph.get_multi_entity_relationships(
                active_characters,
                current_chapter=chapter_num  # 🔥 启用时间窗口优化
            )
        else:
            # 单人场景或无复杂关系，只查简单的邻居
            for char_name in active_characters:
                 neighbors = self.memory.graph.query_entity_context(
                     char_name,
                     current_chapter=chapter_num  # 🔥 启用时间窗口优化
                 )
                 if "暂无" not in neighbors:
                     graph_info += f"## {char_name} 的周边关系\n{neighbors}\n"
        
        # C. 历史记忆碎片
        rag_query = f"{ ' '.join(active_characters)} "
        if intent["type"] == "Combat":
            rag_query += f"战斗 招式 伤痕 弱点 {outline[:50]}"
        elif intent["type"] == "Social":
            rag_query += f"情感 矛盾 承诺 谎言 {outline[:50]}"
        elif intent["type"] == "Investigation":
            rag_query += f"线索 秘密 历史 真相 {outline[:50]}"
        elif intent["type"] == "Introspection":
            rag_query += f"心魔 执念 悟道 {outline[:50]}"
        else:
            rag_query += outline

        if intent.get("needs_history"):
            rag_query += " 往事 历史"

        # 动态增加 k 值，获取更多原始素材供压缩
        rag_content = self.memory.query_related_context(rag_query, k=15 if intent["needs_history"] else 10, current_chapter=chapter_num)
        
        # --- 4. Smart Fit (智能适配) ---
        retrieval_text_raw = f"{char_info}\n{graph_info}\n# 🧠 相关记忆碎片 (基于意图:{intent['type']})\n{rag_content}"
        
        # 调用智能压缩
        retrieval_optimized = self._smart_fit(retrieval_text_raw, retrieval_budget)

        # 获取文风样板
        style_map = {
            "Combat": ["Action", "Scenery"],
            "Social": ["Dialogue", "InnerMonologue"],
            "Investigation": ["InnerMonologue", "Scenery"],
            "Introspection": ["InnerMonologue", "Philosophy"],
            "Travel": ["Scenery"],
            "General": ["Scenery", "Dialogue"]
        }
        target_styles = style_map.get(intent["type"], ["Scenery"])
        style_text = self.memory.get_style_examples(tags=target_styles)

        # 格式化氛围
        atmosphere_text = ""
        if atmosphere:
            atmosphere_text = f"""
# 🌡️ 本章氛围 (Atmosphere)
- 基调 (Tone): {atmosphere.get('tone', 'N/A')}
- 紧张度 (Tension): {atmosphere.get('tension', 'N/A')}
- 感官侧重 (Sensory): {atmosphere.get('sensory_focus', 'N/A')}
- 环境色调 (Color): {atmosphere.get('color_palette', 'N/A')}
"""

        return f"{bible_text}\n{physics_text}\n{vocab_text}\n{state_text}\n{director_instruction}\n{atmosphere_text}\n{style_text}\n{retrieval_optimized}"