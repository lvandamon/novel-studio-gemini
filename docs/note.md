# 启动 Neo4j 容器

docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:latest

# 启动 Frontend
cd frontend && npm run dev

# 启动 Backend API
cd backend && uv run uvicorn api.main:app --reload

# 启动 CLI 应用

uv run python main.py

# 启动 FastAPI 应用

uv run uvicorn api.main:app --reload --port 8000
