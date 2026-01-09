# Infinite-Flow Writer (DeepSeek Edition) - Project Context

## Project Overview
**Infinite-Flow Writer** is a local, AI-assisted writing system designed for creating long-form web novels (2-5 million words). It utilizes a multi-agent architecture powered by DeepSeek models (R1 and V3) to address common challenges in long-form generation: context amnesia, logical inconsistencies, and style drift.

## Tech Stack
*   **Language:** Python 3.10+
*   **Package Manager:** `uv` (Astral)
*   **LLMs:**
    *   **DeepSeek-R1 (Reasoner):** Logic, outlining, consistency checks.
    *   **DeepSeek-V3 (Chat):** Content generation, dialogue, summarization.
*   **Orchestration:** LangChain / LangGraph
*   **Storage:**
    *   **Vector DB:** ChromaDB (Local persistence) for RAG (retrieving settings/past chapters).
    *   **Structured DB:** SQLite for character sheets, items, and relationships.
*   **UI:** Streamlit

## Architecture & Workflow
The system mimics a human editorial team:
1.  **Editor Agent (DeepSeek-R1):** Creates a logical outline for the chapter based on context.
2.  **Writer Agent (DeepSeek-V3):** Writes the prose based on the outline and character settings.
3.  **Reviewer Agent (DeepSeek-R1):** Checks for consistency and style adherence.
4.  **Archivist Agent (DeepSeek-V3):** Extracts new information (facts, items, events) and updates the databases.

## Project Structure
The planned directory structure is as follows:

```text
.
├── pyproject.toml       # Dependency management (PEP 621)
├── uv.lock             # Lockfile
├── .python-version     # Python version pin
├── .env                # Secrets (DEEPSEEK_API_KEY)
├── app.py              # Streamlit entry point
├── core/               # Core infrastructure
│   ├── llm.py          # DeepSeek API wrappers
│   ├── memory.py       # DB adapters (ChromaDB + SQLite)
│   └── prompts.py      # System prompts
├── agents/             # Agent implementations
│   ├── editor_agent.py
│   ├── writer_agent.py
│   ├── reviewer_agent.py
│   └── archivist_agent.py
├── data/               # Local data (Ignored by Git)
│   ├── novel.db        # SQLite
│   └── vector_store/   # ChromaDB
└── utils/              # Helper functions
    └── text_processing.py
```

## Development Guide

### Prerequisites
*   Python 3.10 or higher
*   `uv` package manager installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
*   DeepSeek API Key

### Setup Instructions
1.  **Initialize Project:**
    ```bash
    uv init
    ```
2.  **Install Dependencies:**
    ```bash
    uv add langchain langchain-community chromadb openai streamlit python-dotenv
    ```
3.  **Environment Variables:**
    Create a `.env` file:
    ```ini
    DEEPSEEK_API_KEY=your_key_here
    ```

### Running the Application
Start the local Streamlit interface:
```bash
uv run streamlit run app.py
```

## Implementation Roadmap (Current Status: Initialization)
Refer to `PRD.md` for detailed phases.
- [ ] **Phase 1: Infrastructure:** Setup `uv`, project structure, DB schemas, and basic LLM connectivity.
- [ ] **Phase 2: Core Agents:** Implement Writer and Editor agents.
- [ ] **Phase 3: Memory & RAG:** Implement ChromaDB embedding/retrieval and Reviewer agent.
- [ ] **Phase 4: UI & Integration:** Build Streamlit UI and test full workflow.
