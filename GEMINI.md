# Infinite-Flow Writer (DeepSeek Edition) - Project Context

## Project Overview
**Infinite-Flow Writer** 是一款专为超长篇网文（200-500万字）设计的 AI 辅助写作系统。它通过多智能体协作架构（Multi-Agent Architecture）和分层记忆模型，解决了长程创作中的“设定遗忘”、“人设漂移”和“文风崩坏”三大顽疾。

## Tech Stack
*   **Language:** Python 3.10+
*   **Package Manager:** `uv` (Astral)
*   **LLMs:**
    *   **DeepSeek-R1 (Reasoner):** 核心逻辑、大纲推演、冲突审计、导演决策。
    *   **DeepSeek-V3 (Chat):** 正文撰写、数据提取、分级摘要。
*   **Orchestration:** LangGraph (Stateful Workflow)
*   **Storage:**
    *   **Vector DB:** ChromaDB (分型 RAG：原文碎片 + 世界圣经 + 事件日志)。
    *   **Graph DB:** Neo4j (因果链追溯 + 社交关系网)。
    *   **Structured DB:** SQLite (UUID 角色档案 + 黄金锚点 + 遥测指标 + 分级摘要)。

## Core Architecture Highlights (The "Secret Sauce")
1.  **分形记忆 (Fractal Memory)**: 采用“单章-10章-卷-全局”四级摘要聚合，确保模型永远拥有最精确的上下文视野。
2.  **意图驱动上下文 (Intent-Driven Context)**: 
    *   **Style Injection**: 自动解析剧情类型（战斗/文戏），动态注入对应的《文风样板库》DNA。
    *   **Immutable Anchors**: 强制将角色“黄金锚点”注入 System Prompt，从物理层面杜绝 OOC。
3.  **遥测闭环导演 (Telemetry-Closed Director)**: 
    *   通过 `Reviewer` 生成的真实张力指标（Tension Score）反馈给 `Director`。
    *   `Chaos Engine` 根据真实心流状态决定意外事件的触发频率，实现自适应叙事节奏。
4.  **逻辑守门员 (Archivist Gatekeeper)**: 所有新提取的数据在存库前，必须经过历史事实的二段审计，防止“AI 幻觉”污染世界观。

## Project Structure
```text
.
├── app.py              # Streamlit 交互界面
├── core/               # 核心大脑
│   ├── workflow.py     # LangGraph 状态机定义
│   ├── context_manager.py # 分层级上下文构建 (意图驱动)
│   ├── memory.py       # 混合数据库适配器 (SQLite + Chroma)
│   ├── graph_store.py  # 知识图谱 (Neo4j) 管理器
│   └── chaos.py        # 熵增引擎 (意外事件生成器)
├── agents/             # 专家智能体
│   ├── director_agent.py # 宏观审计与节奏控制
│   ├── editor_agent.py   # 细纲推演与节拍把控
│   ├── writer_agent.py   # 沉浸式正文生成 (V3)
│   ├── simulator_agent.py # 心理沙盘与行为模拟
│   ├── reviewer_agent.py # 遥测指标分析与逻辑审计
│   └── archivist_agent.py # 数据提取与一致性校验
├── tests/              # 自动化测试套件
├── data/               # 数据库文件 (Git Ignore)
└── utils/              # 世界观初始化工具
```

## Implementation Roadmap
- [x] **Phase 1: Infrastructure:** `uv` 环境搭建，SQLite/Chroma 基础 Schema，UUID 角色管理。
- [x] **Phase 2: Core Agents:** 实装 Writer, Editor, Director。完成 Director 遥测闭环。
- [x] **Phase 3: Context & Style:** 实装意图驱动上下文管理器，黄金锚点与文风样板库。
- [ ] **Phase 4: Advanced Graph:** 强化 Neo4j 因果链追溯，实装“蝴蝶效应”分析。
- [ ] **Phase 5: UI & Scale:** Streamlit 交互界面优化，进行 10 万字压力连贯性测试。

## Quick Start
```bash
# 安装依赖
uv sync

# 初始化世界设定与文风
uv run python utils/init_world_v2.py
uv run python utils/init_style.py

# 运行流程测试
uv run python tests/test_workflow_v2.py
```