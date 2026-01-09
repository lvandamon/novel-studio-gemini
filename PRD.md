项目计划书：无限流·DeepSeek 小说创作系统

1. 项目概述 (Project Overview)

项目名称：Infinite-Flow Writer (DeepSeek Edition)
项目目标：构建一套基于 DeepSeek 双模型驱动的本地化 AI 辅助写作系统，旨在解决长篇网络小说（200 万-500 万字）创作过程中的“遗忘”、“逻辑崩坏”和“高成本”问题。
核心理念：将“清风揽岳”的创作人格代码化，从“单次对话”转变为“智能体协作流（Agent Workflow）”，利用外部数据库实现永久记忆。

2. 核心问题与解决方案 (Core Issues & Solutions)

核心痛点

传统 Prompt 模式的问题

本系统解决方案

记忆遗忘

上下文窗口有限，写到第 50 章忘了第 1 章设定。

RAG (检索增强生成)：将设定和旧文存入向量库，按需检索。

逻辑崩坏

战力崩坏、人物性格前后不一、伏笔未回收。

DeepSeek-R1 (推理模型)：在写作前进行深度逻辑校验和推理。

风格漂移

越写越像 AI 机器人，失去“清风揽岳”的文风。

动态 Few-Shot：每次写作前，检索作者过去的高分片段作为参考范文。

成本高昂

长篇巨制 Token 消耗呈指数级增长。

DeepSeek API + 缓存：利用 DeepSeek 低价优势及 Context Caching 技术。

3. 技术选型 (Technology Stack)

3.1 核心大模型 (LLM)

逻辑/大纲/审核核心：DeepSeek-R1 (Reasoner)

用途：剧情推演、一致性检查、大纲拆解、伏笔管理。

创作/扩写核心：DeepSeek-V3 (Chat)

用途：正文撰写、场景描写、对话生成、总结摘要。

3.2 开发环境与架构 (Local Architecture)

运行模式：Local Only (纯本地运行)

无需服务器，数据存储在本地文件系统，隐私性最高。

开发语言：Python 3.10+

包管理器：uv (Astral 出品的高性能包管理器)

优势：极速安装依赖，自动管理虚拟环境。

依赖管理：pyproject.toml

标准：使用 PEP 621 标准管理项目依赖。

Agent 编排框架：LangChain 或 LangGraph (推荐 LangGraph)。

向量数据库 (Vector DB)：ChromaDB (Persistent Client)

配置：配置为本地持久化存储 (./data/vector_store)。

结构化数据库：SQLite

配置：Python 内置，无需安装额外服务，单文件存储 (./data/novel.db)。

3.3 本地交互界面

Streamlit：用于快速构建本地 Web GUI，启动只需 uv run streamlit run app.py。

4. 核心架构 (Core Architecture)

系统采用 “主编-作家-书评人” 三位一体的智能体架构：

graph TD
User[用户/作者] --> UI[本地 Streamlit 界面]
UI --> Orchestrator[中控调度器 (LangGraph)]

    subgraph "大脑 (DeepSeek-R1)"
        Editor[主编 Agent] -- 1.制定本章细纲 --> Orchestrator
        Reviewer[书评人 Agent] -- 3.逻辑一致性检查 --> Orchestrator
    end

    subgraph "双手 (DeepSeek-V3)"
        Writer[作家 Agent] -- 2.撰写正文 --> Orchestrator
        Archivist[档案员 Agent] -- 4.提取新设定/存入记忆 --> Database
    end

    subgraph "本地记忆体 (Local Storage)"
        VectorDB[(ChromaDB: 正文/风格)]
        SQL[(SQLite: 角色/物品/关系)]
    end

    Orchestrator <--> VectorDB
    Orchestrator <--> SQL

5. 项目结构 (Project Structure)

InfiniteFlow-Writer/
├── pyproject.toml # [新增] 核心依赖配置文件 (uv init 生成)
├── uv.lock # [新增] 依赖锁定文件
├── .python-version # [新增] 指定 Python 版本
├── app.py # 启动入口 (Streamlit)
├── .env # 存放 DEEPSEEK_API_KEY
├── core/
│ ├── llm.py # 封装 DeepSeek V3/R1 调用
│ ├── memory.py # 封装 ChromaDB + SQLite 本地存储
│ └── prompts.py # 存放“清风揽岳”的所有 Prompt 模板
├── agents/ # 智能体逻辑
│ ├── editor_agent.py # R1: 负责大纲和逻辑
│ ├── writer_agent.py # V3: 负责正文扩写
│ ├── reviewer_agent.py # R1: 负责审核和修稿
│ └── archivist_agent.py # V3: 负责数据更新
├── data/ # 本地数据存储 (在 .gitignore 中忽略)
│ ├── novel.db # SQLite 文件
│ └── vector_store/ # ChromaDB 持久化目录
└── utils/
└── text_processing.py # 文本切分、Token 计算工具

6. 关键实现细节 (Key Implementation Details)

A. “世界圣经”的数据结构设计

这是系统一致性的基石。你需要定义标准的 JSON Schema：

// 角色卡示例
{
"name": "萧风",
"status": "存活",
"current_level": "元婴期",
"personality": ["冷酷", "护短", "谨慎"],
"relationships": {"林月": "师妹/暗恋对象", "黑魔老祖": "死敌"},
"inventory": ["青云剑", "九转还魂丹"],
"dynamic_state": "当前身受重伤，位于幽冥谷"
}

B. 上下文组装逻辑 (Context Builder)

在生成第 500 章时，Prompt 不再是静态的，而是由代码动态生成的：

全局设定：读取世界观摘要 (500 tokens)。

当前状态：读取主角当前的 JSON 状态 (200 tokens)。

相关记忆：搜索 ChromaDB 中与“当前场景关键词”相似度最高的 3 个旧章节片段 (2000 tokens)。

前情提要：读取第 499 章的摘要 (500 tokens)。

任务指令：R1 生成的本章逻辑细纲。

C. DeepSeek 上下文缓存 (Context Caching)

为了省钱，将**“世界观设定”、“人物小传”**等不常变的内容，利用 DeepSeek 的 Caching 功能进行标记。这样每次请求时，这部分 Input Token 不会计费（或极低）。

7. 实现步骤 (Implementation Steps)

第一阶段：基础设施搭建 (Week 1)

环境初始化：

安装 uv: curl -LsSf https://astral.sh/uv/install.sh | sh (或 pip install uv)

初始化项目: uv init InfiniteFlow-Writer

添加依赖: uv add langchain langchain-community chromadb openai streamlit python-dotenv

API 联调：编写 core/llm.py，确保能分别调用 deepseek-chat 和 deepseek-reasoner。

数据库初始化：编写 Python 脚本创建 SQLite 表结构（Chapters, Characters, Items），设计 JSON 模板。

第二阶段：核心智能体开发 (Week 2)

作家 Agent：实现“给定大纲+人设 -> 生成 3000 字正文”的功能。

主编 Agent：实现“给定前情提要 -> 生成本章逻辑细纲”的功能 (Chain of Thought)。

串联测试：手动输入前情，使用 uv run python test_flow.py 测试 R1 生成大纲 -> V3 生成正文的流程。

第三阶段：记忆系统与 RAG (Week 3)

向量化存储：实现每写完一章，自动 Embedding 并存入 ChromaDB 本地文件夹。

检索逻辑：写代码实现“在写打斗戏时，自动检索主角有哪些技能”。

一致性检查：接入 Reviewer Agent，对比正文与检索到的设定，报错并自动让 Writer 重写。

第四阶段：界面与全流程跑通 (Week 4)

UI 开发：用 Streamlit 做一个简单的界面。

启动命令: uv run streamlit run app.py

长文测试：尝试连续生成 5-10 章，观察记忆是否生效，逻辑是否连贯。

微调 Prompt：根据生成效果，调整“清风揽岳”的 System Prompt。

8. 预估工作量 (Estimated Workload)

开发者要求：1 名具备 Python 基础的全栈开发者（或你自己）。

总工时：约 80 - 120 小时。

API 成本预估：开发测试阶段约 50 元人民币；成书阶段（200 万字）约 200-500 元人民币（视 R1 调用频率而定）。

9. 环境要求 (Environment)

操作系统：Windows / macOS / Linux 均可。

硬件：

CPU: 任意现代多核 CPU。

内存: 建议 16GB+ (ChromaDB 和浏览器会占用一些内存)。

硬盘: 建议 SSD，至少预留 10GB 空间用于存储生成的文本和向量索引。

网络：需能稳定访问 DeepSeek API。

API Key：DeepSeek API Key。
