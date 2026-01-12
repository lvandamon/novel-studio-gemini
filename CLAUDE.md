# CLAUDE.md - Novel Studio Gemini

## Project Overview

Novel Studio Gemini is an AI-assisted creative writing system for ultra-long Chinese web novels (2-5 million words). It uses multi-agent orchestration to solve memory leaks, logical inconsistencies, and style degradation in long-form novel generation.

## Tech Stack

- **Language**: Python 3.12+
- **Package Manager**: uv (Astral)
- **LLMs**: DeepSeek-R1 (reasoning) + DeepSeek-V3 (writing)
- **Orchestration**: LangGraph
- **Storage**: ChromaDB (vectors) + SQLite (structured) + Neo4j (graph)
- **UI**: Streamlit (dashboard) + cmd.Cmd (CLI)
- **Embeddings**: SentenceTransformers (all-MiniLM-L6-v2)

## Quick Commands

```bash
# Install dependencies
uv sync

# Initialize world data (required first time)
uv run python utils/init_world_v2.py
uv run python utils/init_style.py

# Run CLI
uv run python main.py

# Run Streamlit dashboard
uv run streamlit run app.py

# Run tests
pytest tests/
uv run python tests/test_workflow_v2.py
```

## Project Structure

```
core/           # Core modules (workflow, memory, context, graph, llm, prompts, schemas)
agents/         # AI agents (director, editor, writer, reviewer, archivist, simulator, etc.)
utils/          # Initialization scripts (init_world_v2.py, init_plan.py, init_style.py)
tests/          # Test suite
pages/          # Streamlit multi-page extensions
data/           # Local storage (SQLite, ChromaDB) - git-ignored
```

## Key Files

- `core/workflow.py` - LangGraph state machine & workflow nodes
- `core/memory.py` - MemoryManager (SQLite + ChromaDB adapters)
- `core/prompts.py` - All system prompts and templates
- `core/schemas.py` - Pydantic models (CharacterSchema, EventSchema, etc.)
- `core/physics.py` - PhysicalityEngine (hard logic constraints)
- `core/graph_store.py` - Neo4j integration

## Agent Workflow

```
INPUT → Director Check → Editor Planning → Writer Execution
      → Simulator Feedback → Reviewer Audit → Archivist Archive → OUTPUT
```

## Key Agents

| Agent | LLM | Role |
|-------|-----|------|
| Director | R1 | Strategic oversight, tension metrics (every 5 chapters) |
| Editor | R1 | Chapter outline generation, beat planning |
| Writer | V3 | Prose generation with Draft→Critique→Refine loop |
| Reviewer | R1 | Logic auditing, contradiction detection |
| Archivist | V3 | Data extraction, memory persistence |

## Memory Architecture

1. **ChromaDB**: Semantic search (novel_content, novel_events collections)
2. **SQLite**: Structured data (characters, chapters, events, items, world_bible, telemetry)
3. **Neo4j**: Relationship graph, causal chains, entity networks

## Code Patterns

### JSON Cleaning for Reasoner Models
Agents use `_clean_json()` to handle DeepSeek-R1's `<think>` blocks and extract JSON.

### Lazy-Loaded Agents
Agents initialized on-demand via properties to minimize startup overhead.

### Context Budget Management
`ContextManager` uses token counting with semantic compression and physical trimming.

### Neo4j Retry Decorator
Graph operations use `@retry_neo4j(max_retries=3)` for exponential backoff.

## Environment

- Requires `.env` file with `DEEPSEEK_API_KEY`
- Uses Chinese character names and xianxia cultivation terminology
- Fictional calendar: 天道历 (Heavenly Dao Calendar)

## Recent Features

- **Rollback Authority**: Director can force rewrites
- **Hard Physiological Logic**: Tracks permanent injuries/body status
- **Causal Integrity**: Neo4j-enforced consistency
- **Graveyard Mechanism**: Archives dead character memories
- **Golden Anchors**: Immutable personality traits
- **Time-Decay RAG**: Memory retrieval with temporal decay
