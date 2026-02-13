"""RAG (Retrieval-Augmented Generation) module for Open Interpreter.

Provides semantic search over a local codebase via an external
embedding service and ChromaDB for vector storage.
"""

import hashlib
import os
import pathlib
from typing import Any, Dict, List, Optional

import requests

# chromadb is an optional dependency (pip install open-interpreter[rag])
try:
    import chromadb
except ImportError:
    chromadb = None

# Directories / file extensions to skip when indexing
_SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    "venv",
    ".venv",
    "env",
    ".env",
    ".tox",
    ".nox",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".eggs",
    "*.egg-info",
}

_MAX_FILE_SIZE = 1_000_000  # 1 MB

_CHUNK_SIZE = 800  # characters per chunk
_CHUNK_OVERLAP = 100  # character overlap between chunks


class Rag:
    """Semantic code search via embeddings + ChromaDB.

    Designed to be mounted on ``Computer`` as ``computer.rag``.
    """

    def __init__(self, computer):
        self.computer = computer
        self.embedding_service_url: str = os.getenv(
            "EMBEDDING_SERVICE_URL", "http://localhost:8100"
        )
        self._chroma_persist_dir: str = os.getenv(
            "CHROMA_PERSIST_DIR",
            os.path.join(pathlib.Path.home(), ".open-interpreter", "rag"),
        )
        self._chroma_client = None
        self._indexed_dir: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API (auto-documented in the Computer API system message)
    # ------------------------------------------------------------------

    def index(self, path=None):
        """Walk a directory, chunk code files, embed them and store in ChromaDB."""
        if chromadb is None:
            raise ImportError(
                "chromadb is required for RAG. Install with: pip install open-interpreter[rag]"
            )

        path = path or os.getcwd()
        path = os.path.abspath(path)
        self._indexed_dir = path

        collection = self._get_or_create_collection(path)

        file_count = 0
        chunk_count = 0

        for root, dirs, files in os.walk(path):
            # Prune directories we never want to descend into
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]

            for fname in files:
                fpath = os.path.join(root, fname)
                try:
                    if os.path.getsize(fpath) > _MAX_FILE_SIZE:
                        continue
                    with open(fpath, "r", errors="ignore") as fh:
                        content = fh.read()
                except (OSError, UnicodeDecodeError):
                    continue

                chunks = self._chunk_file(fpath, content)
                if not chunks:
                    continue

                ids = [
                    hashlib.md5(
                        f"{fpath}:{i}".encode()
                    ).hexdigest()
                    for i in range(len(chunks))
                ]
                embeddings = self._get_embeddings(chunks)
                if embeddings is None:
                    continue  # embedding service unreachable – skip

                metadatas = [
                    {"filepath": fpath, "chunk_index": i}
                    for i in range(len(chunks))
                ]

                collection.upsert(
                    ids=ids,
                    embeddings=embeddings,
                    documents=chunks,
                    metadatas=metadatas,
                )

                file_count += 1
                chunk_count += len(chunks)

        return {"files": file_count, "chunks": chunk_count}

    def search(self, query, n_results=5):
        """Embed *query* and return the most relevant code chunks from ChromaDB."""
        if chromadb is None:
            raise ImportError(
                "chromadb is required for RAG. Install with: pip install open-interpreter[rag]"
            )

        if self._indexed_dir is None:
            return []

        collection = self._get_or_create_collection(self._indexed_dir)

        embeddings = self._get_embeddings([query])
        if embeddings is None:
            return []

        results = collection.query(
            query_embeddings=embeddings,
            n_results=n_results,
        )

        output: List[Dict[str, Any]] = []
        if results and results.get("documents"):
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            dists = results["distances"][0] if results.get("distances") else [0.0] * len(docs)
            for doc, meta, dist in zip(docs, metas, dists):
                output.append(
                    {
                        "filepath": meta.get("filepath", ""),
                        "content": doc,
                        "score": 1.0 - dist,  # cosine distance → similarity
                    }
                )
        return output

    def status(self):
        """Return current RAG status information."""
        reachable = self._embedding_service_reachable()

        if chromadb is None or self._indexed_dir is None:
            return {
                "files": 0,
                "chunks": 0,
                "indexed": False,
                "embedding_service_reachable": reachable,
            }

        try:
            collection = self._get_or_create_collection(self._indexed_dir)
            count = collection.count()
        except Exception:
            count = 0

        return {
            "files": 0,  # ChromaDB doesn't track unique files; approximate via count
            "chunks": count,
            "indexed": count > 0,
            "embedding_service_reachable": reachable,
        }

    def clear(self):
        """Drop the current ChromaDB collection."""
        if chromadb is None or self._indexed_dir is None:
            return

        client = self._get_chroma_client()
        col_name = self._collection_name(self._indexed_dir)
        try:
            client.delete_collection(col_name)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_embeddings(self, texts: List[str]) -> Optional[List[List[float]]]:
        """Call the external embedding service. Returns *None* on failure."""
        try:
            resp = requests.post(
                f"{self.embedding_service_url}/embed",
                json={"texts": texts},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["embeddings"]
        except Exception:
            return None

    def _chunk_file(self, filepath: str, content: str) -> List[str]:
        """Split *content* into line-boundary-aware chunks."""
        if not content.strip():
            return []

        chunks: List[str] = []
        start = 0
        length = len(content)
        while start < length:
            end = start + _CHUNK_SIZE
            # Try to break at a newline
            if end < length:
                newline_pos = content.rfind("\n", start, end)
                if newline_pos > start:
                    end = newline_pos + 1  # include the newline
            chunk = content[start:end]
            if chunk.strip():
                chunks.append(chunk)
            start = end - _CHUNK_OVERLAP if end < length else length
        return chunks

    def _get_chroma_client(self):
        """Lazy-init a ChromaDB PersistentClient."""
        if self._chroma_client is None:
            os.makedirs(self._chroma_persist_dir, exist_ok=True)
            self._chroma_client = chromadb.PersistentClient(
                path=self._chroma_persist_dir
            )
        return self._chroma_client

    def _get_or_create_collection(self, directory: str):
        """Return (or create) the ChromaDB collection for *directory*."""
        client = self._get_chroma_client()
        return client.get_or_create_collection(
            name=self._collection_name(directory),
        )

    @staticmethod
    def _collection_name(directory: str) -> str:
        """Deterministic collection name derived from the indexed directory."""
        dir_hash = hashlib.md5(directory.encode()).hexdigest()[:16]
        return f"rag_{dir_hash}"

    def _embedding_service_reachable(self) -> bool:
        try:
            resp = requests.get(
                f"{self.embedding_service_url}/health", timeout=5
            )
            return resp.status_code == 200
        except Exception:
            return False
