# Infinite-Flow Writer (DeepSeek Edition)

**Infinite-Flow Writer** (Novel Studio) 是一款专为超长篇网文（200-500万字）设计的 AI 辅助写作系统。它通过多智能体协作架构（Multi-Agent Architecture）和分层记忆模型，解决了长程创作中的“设定遗忘”、“人设漂移”和“文风崩坏”三大顽疾。

---

## 🚀 项目核心亮点 (The "Secret Sauce")

1.  **分形记忆 (Fractal Memory)**: 采用“单章-10章-卷-全局”四级摘要聚合，确保模型永远拥有最精确的上下文视野。
2.  **意图驱动上下文 (Intent-Driven Context)**: 
    *   **Style Injection**: 自动解析剧情类型（战斗/文戏），动态注入对应的《文风样板库》DNA。
    *   **Immutable Anchors**: 强制将角色“黄金锚点”注入 System Prompt，从物理层面杜绝 OOC。
3.  **遥测闭环导演 (Telemetry-Closed Director)**: 
    *   通过 `Reviewer` 生成的真实张力指标（Tension Score）反馈给 `Director`。
    *   `Chaos Engine` 根据真实心流状态决定意外事件的触发频率，实现自适应叙事节奏。
4.  **逻辑守门员 (Archivist Gatekeeper)**: 所有新提取的数据在存库前，必须经过历史事实的二段审计，防止“AI 幻觉”污染世界观。

---

## 🛠️ 技术栈

*   **语言:** Python 3.12+
*   **包管理:** `uv` (Astral)
*   **大模型:**
    *   **DeepSeek-R1 (Reasoner):** 核心逻辑、大纲推演、冲突审计、导演决策。
    *   **DeepSeek-V3 (Chat):** 正文撰写、数据提取、分级摘要。
*   **编排:** LangGraph (Stateful Workflow)
*   **存储:**
    *   **Vector DB:** ChromaDB (分型 RAG：原文碎片 + 世界圣经 + 事件日志)。
    *   **Graph DB:** Neo4j (因果链追溯 + 社交关系网)。
    *   **Structured DB:** SQLite (UUID 角色档案 + 黄金锚点 + 遥测指标 + 分级摘要)。

---

## 📦 环境设置

项目使用 `uv` 进行高效的依赖管理。

1.  **安装 `uv`** (如果尚未安装):
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

2.  **同步环境**:
    ```bash
    uv sync
    ```

3.  **配置环境变量**:
    在根目录下创建 `.env` 文件，并配置必要的 API 密钥和数据库连接信息：
    ```env
    OPENAI_API_KEY=your_key_here
    OPENAI_BASE_URL=https://api.deepseek.com
    NEO4J_URI=bolt://localhost:7687
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=your_password
    ```

---

## 🏃 启动与初始化

在首次运行前，需要初始化世界观设定和文风库。

1.  **初始化基础数据**:
    ```bash
    # 初始化世界设定
    uv run python utils/init_world_v2.py
    # 初始化文风库
    uv run python utils/init_style.py
    ```

2.  **启动后端服务**:
    ```bash
    cd backend
    uv run uvicorn api.main:app --reload
    ```

3.  **启动前端界面**:
    ```bash
    cd frontend
    npm install
    npm run dev
    ```

---

## 🧪 自动化测试

项目包含完整的测试套件，涵盖核心逻辑、智能体协作和工作流。

1.  **运行所有测试**:
    ```bash
    uv run pytest
    ```

2.  **运行特定模块测试**:
    ```bash
    # 测试工作流
    uv run python tests/test_workflow_v2.py
    # 测试遥测系统
    uv run pytest tests/test_telemetry.py
    ```

---

## 📂 项目结构

```text
.
├── frontend/           # React 交互界面 (主入口)
├── backend/            # Python 后端
│   ├── main.py         # CLI 入口
│   ├── api/            # FastAPI 服务
│   ├── agents/         # 专家智能体
│   ├── core/           # 核心大脑
│   └── ...
├── data/               # 数据库文件 (Vector Store, SQLite)
├── utils/              # 初始化与实用工具
├── tests/              # 自动化测试套件
└── pyproject.toml      # 依赖与配置
```
