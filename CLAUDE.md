# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A RAG (Retrieval-Augmented Generation) chatbot for course materials. Python/FastAPI backend with a vanilla JavaScript frontend. Users ask questions about course content, which are answered via semantic search (ChromaDB) + Claude AI response generation with tool use.

## Commands

### Install dependencies
```bash
uv sync
```

### Run the application
```bash
cd backend && uv run uvicorn app:app --reload --port 8000
```
Or use `./run.sh` from the project root.

- Web UI: http://localhost:8000
- API docs (Swagger): http://localhost:8000/docs

### Environment setup
Copy `.env.example` to `.env` in the project root and set `ANTHROPIC_API_KEY`.

## Architecture

### Request flow
1. Frontend (`frontend/script.js`) sends POST to `/api/query` with `{query, session_id}`
2. `backend/app.py` FastAPI endpoint delegates to `RAGSystem.query()`
3. `RAGSystem` (orchestrator) calls `AIGenerator.generate_response()` with tool definitions
4. Claude decides whether to invoke the `search_course_content` tool
5. If tool is called: `ToolManager` dispatches to `CourseSearchTool` which queries `VectorStore` (ChromaDB)
6. Claude synthesizes the search results into a final response
7. `SessionManager` records the exchange for conversation continuity

### Backend components (`backend/`)

| File | Responsibility |
|---|---|
| `app.py` | FastAPI app, API endpoints, static file serving, startup document loading |
| `rag_system.py` | Orchestrator — wires together all components |
| `vector_store.py` | ChromaDB wrapper with two collections: `course_catalog` (metadata) and `course_content` (chunks) |
| `ai_generator.py` | Anthropic Claude API calls with tool-use loop |
| `document_processor.py` | Parses course text files, extracts metadata/lessons, chunks text (800 chars, 100 overlap) |
| `search_tools.py` | `CourseSearchTool` and `ToolManager` — tool definitions and execution for Claude tool use |
| `session_manager.py` | In-memory conversation history (max 2 exchanges per session, lost on restart) |
| `models.py` | Pydantic/dataclass models: `Course`, `Lesson`, `CourseChunk` |
| `config.py` | Centralized config loaded from env vars and defaults |

### Frontend (`frontend/`)
Vanilla HTML/CSS/JS chat interface. No build step. Served as static files by FastAPI. `script.js` handles API communication and DOM updates.

### Key configuration (`backend/config.py`)
- Model: `claude-sonnet-4-20250514`
- Embeddings: `all-MiniLM-L6-v2` (SentenceTransformer)
- Chunk size: 800 chars with 100 char overlap
- ChromaDB stored at `./chroma_db` (relative to backend dir)

### Course documents
Text files in `docs/` with structured format: title, instructor, course link on the first lines, then `Lesson N: Title` markers throughout. `DocumentProcessor` parses this structure during startup.

### API endpoints
- `POST /api/query` — main query endpoint (`{query, session_id}` -> `{answer, sources, session_id}`)
- `GET /api/courses` — returns course count and titles
- `GET /` — serves frontend static files

## Dependencies

Managed with `uv` (pyproject.toml + uv.lock). Requires Python >= 3.13. Core deps: `fastapi`, `uvicorn`, `anthropic`, `chromadb`, `sentence-transformers`, `python-dotenv`, `python-multipart`.

## Notes

- No test suite exists in the project currently.
- The server must be started from the `backend/` directory (or via `run.sh`) because relative paths reference `../docs` and `../frontend`.
- ChromaDB data persists in `backend/chroma_db/`. On startup, existing courses are skipped (deduplication by title). Pass `clear_existing=True` to `add_course_folder()` to rebuild.
- Sessions are in-memory only — all conversation history is lost on server restart.
