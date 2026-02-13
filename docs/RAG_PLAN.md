# RAG for Open Interpreter — Implementation Plan

## Context
Open Interpreter doesn't understand full repository context — it only sees what fits in the LLM's context window. We're adding RAG so the LLM can semantically search the codebase and receive relevant snippets automatically.

Architecture: **sentence-transformers** in a GPU Docker container (remote-capable) + **ChromaDB** locally + a new `computer.rag` module following existing Computer API patterns.

---

## Part 1: Docker Embedding Service

**Create `docker/embedding-service/`**

| File | Purpose |
|------|---------|
| `Dockerfile` | nvidia/cuda base, installs sentence-transformers + FastAPI + uvicorn, bakes in `all-MiniLM-L6-v2` model at build time |
| `app.py` | FastAPI with `POST /embed` (batch texts → embeddings) and `GET /health` |
| `requirements.txt` | sentence-transformers, fastapi, uvicorn |
| `docker-compose.yml` | Exposes port 8100, GPU reservation, `EMBEDDING_MODEL` env var |

---

## Part 2: RAG Module

**Create `interpreter/core/computer/rag/`**

| File | Purpose |
|------|---------|
| `__init__.py` | Empty |
| `rag.py` | `Rag` class with `__init__(self, computer)` |

### `Rag` class — public methods (auto-documented in system message):
- **`index(path=None)`** — walks directory, chunks code files, sends to embedding service, upserts into ChromaDB. Skips `.git`, `node_modules`, `__pycache__`, `venv`, etc. Caps files at 1MB.
- **`search(query, n_results=5)`** — embeds query via service, queries ChromaDB, returns list of `{filepath, content, score}`
- **`status()`** — returns `{files, chunks, indexed, embedding_service_reachable}`
- **`clear()`** — drops ChromaDB collection

### Config (from env):
- `EMBEDDING_SERVICE_URL` (default `http://localhost:8100`)
- `CHROMA_PERSIST_DIR` (default `~/.open-interpreter/rag`)

### Private methods:
- `_get_embeddings(texts)` — calls `POST {url}/embed`, returns vectors
- `_chunk_file(filepath, content)` — splits on line boundaries, ~800 chars per chunk, 100 char overlap
- `_get_chroma_client()` — lazy-inits `chromadb.PersistentClient`, collection named by hash of indexed dir

---

## Part 3: Wire into Computer API

**Modify `interpreter/core/computer/computer.py`:**
1. Add `from .rag.rag import Rag` (line ~4, with other imports)
2. Add `self.rag = Rag(self)` (line ~46, after `self.files`)

The existing `_get_all_computer_tools_signature_and_description()` auto-discovers methods on registered tools — `rag.search()`, `rag.index()`, etc. will appear in the system message automatically via the Computer API block.

---

## Part 4: Auto-inject RAG context in respond.py

**Modify `interpreter/core/respond.py`** — after the computer API system message block (after line 58), add:

When RAG is indexed and the latest message is from the user, automatically `search(user_query)` and append relevant snippets to the system message under a `# RELEVANT CODEBASE CONTEXT` header. Limited to 5 results. Wrapped in try/except so RAG failure never blocks the conversation.

---

## Part 5: RAG Profile

**Create `interpreter/terminal_interface/profiles/defaults/rag.py`:**
- Loads `.env` via dotenv
- Configures `computer.rag.embedding_service_url` from env
- Auto-indexes `os.getcwd()` on startup
- Sets `computer.import_computer_api = True`
- Adds `custom_instructions` telling the LLM about `computer.rag.search()`
- Uses `OI_MODEL` env var for LLM selection (default: anthropic)
- Sets `safe_mode = "ask"`

---

## Part 6: Config updates

**Modify `.env.example`** — add:
```
EMBEDDING_SERVICE_URL=http://localhost:8100
CHROMA_PERSIST_DIR=~/.open-interpreter/rag
OI_MODEL=anthropic/claude-sonnet-4-5-20250929
```

**Modify `pyproject.toml`** — add `chromadb` as optional dependency under a `[rag]` extra:
```toml
chromadb = { version = "^0.5.0", optional = true }
# In extras:
rag = ["chromadb"]
```

---

## Implementation Order

1. Docker embedding service (independent)
2. `interpreter/core/computer/rag/` module
3. `computer.py` integration (depends on 2)
4. `respond.py` context injection (depends on 2)
5. Profile + config (depends on 2-4)

Steps 1 and 2 can be done in parallel.

---

## Verification

1. **Docker**: `docker compose up`, then `curl -X POST http://localhost:8100/embed -d '{"texts":["hello"]}'` returns embeddings
2. **Index**: `open-interpreter --profile rag` → should see "Indexing..." then "RAG ready: X files, Y chunks"
3. **Search**: Ask "where is the safe_mode setting defined?" → LLM response should reference `core.py` and `start_terminal_interface.py` accurately
4. **Fallback**: Stop Docker container → interpreter should still work, just without RAG context
5. **Re-index**: In conversation, run `computer.rag.index()` → should re-index successfully
