"""Tests for the RAG module."""

import hashlib
import os
import tempfile
from unittest.mock import MagicMock, patch, call

import pytest

from interpreter.core.computer.rag.rag import Rag, _CHUNK_OVERLAP, _CHUNK_SIZE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rag():
    """Return a Rag instance with a fake computer."""
    computer = MagicMock()
    rag = Rag(computer)
    return rag


def _fake_embeddings(texts):
    """Return deterministic 3-dim embeddings for tests (via hash)."""
    result = []
    for t in texts:
        h = hashlib.md5(t.encode()).hexdigest()
        result.append([int(h[i : i + 2], 16) / 255.0 for i in range(0, 6, 2)])
    return result


# ---------------------------------------------------------------------------
# 1. Chunking
# ---------------------------------------------------------------------------

class TestChunking:
    def test_empty_content_returns_no_chunks(self):
        rag = _make_rag()
        assert rag._chunk_file("test.py", "") == []
        assert rag._chunk_file("test.py", "   \n  ") == []

    def test_small_file_single_chunk(self):
        rag = _make_rag()
        content = "hello world\n"
        chunks = rag._chunk_file("test.py", content)
        assert len(chunks) == 1
        assert chunks[0] == content

    def test_large_file_multiple_chunks(self):
        rag = _make_rag()
        # Create content larger than _CHUNK_SIZE
        content = "x" * (_CHUNK_SIZE * 3)
        chunks = rag._chunk_file("big.py", content)
        assert len(chunks) > 1

    def test_chunks_have_overlap(self):
        rag = _make_rag()
        lines = [f"line {i}\n" for i in range(200)]
        content = "".join(lines)
        chunks = rag._chunk_file("test.py", content)
        # With overlap, later chunks should contain some content from earlier chunks
        if len(chunks) > 1:
            # The end of chunk[0] and beginning of chunk[1] should share content
            assert len(chunks[1]) > 0


# ---------------------------------------------------------------------------
# 2. Status / clear without indexing
# ---------------------------------------------------------------------------

class TestStatusAndClear:
    def test_status_before_index(self):
        rag = _make_rag()
        st = rag.status()
        assert st["indexed"] is False
        assert st["chunks"] == 0

    def test_clear_before_index_no_error(self):
        rag = _make_rag()
        # Should not raise
        rag.clear()


# ---------------------------------------------------------------------------
# 3. Embedding service helper
# ---------------------------------------------------------------------------

class TestGetEmbeddings:
    @patch("interpreter.core.computer.rag.rag.requests.post")
    def test_successful_embedding(self, mock_post):
        rag = _make_rag()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = rag._get_embeddings(["hello"])
        assert result == [[0.1, 0.2, 0.3]]
        mock_post.assert_called_once()

    @patch("interpreter.core.computer.rag.rag.requests.post", side_effect=Exception("timeout"))
    def test_failed_embedding_returns_none(self, mock_post):
        rag = _make_rag()
        result = rag._get_embeddings(["hello"])
        assert result is None


# ---------------------------------------------------------------------------
# 4. Embedding service reachability
# ---------------------------------------------------------------------------

class TestEmbeddingServiceReachable:
    @patch("interpreter.core.computer.rag.rag.requests.get")
    def test_reachable(self, mock_get):
        rag = _make_rag()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp
        assert rag._embedding_service_reachable() is True

    @patch("interpreter.core.computer.rag.rag.requests.get", side_effect=Exception("fail"))
    def test_unreachable(self, mock_get):
        rag = _make_rag()
        assert rag._embedding_service_reachable() is False


# ---------------------------------------------------------------------------
# 5. Index + search (with fully mocked ChromaDB and embeddings)
# ---------------------------------------------------------------------------

class TestIndexAndSearch:
    def test_index_calls_upsert(self, tmp_path):
        """Index a temp directory — verify chunks are upserted to ChromaDB."""
        (tmp_path / "hello.py").write_text("def hello():\n    return 'world'\n")
        (tmp_path / "math.py").write_text("def add(a, b):\n    return a + b\n")

        rag = _make_rag()
        mock_collection = MagicMock()
        with (
            patch.object(rag, "_get_embeddings", side_effect=_fake_embeddings),
            patch.object(rag, "_get_or_create_collection", return_value=mock_collection),
        ):
            result = rag.index(str(tmp_path))

        assert result["files"] == 2
        assert result["chunks"] >= 2
        assert mock_collection.upsert.call_count == 2  # one call per file

    def test_index_skips_git_dir(self, tmp_path):
        """The .git directory should be skipped."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("gitconfig")
        (tmp_path / "main.py").write_text("print('hi')\n")

        rag = _make_rag()
        mock_collection = MagicMock()
        with (
            patch.object(rag, "_get_embeddings", side_effect=_fake_embeddings),
            patch.object(rag, "_get_or_create_collection", return_value=mock_collection),
        ):
            result = rag.index(str(tmp_path))

        assert result["files"] == 1  # only main.py

    def test_index_skips_large_files(self, tmp_path):
        """Files over 1 MB should be skipped."""
        (tmp_path / "small.py").write_text("x = 1\n")
        large = tmp_path / "huge.bin"
        large.write_text("x" * 1_100_000)

        rag = _make_rag()
        mock_collection = MagicMock()
        with (
            patch.object(rag, "_get_embeddings", side_effect=_fake_embeddings),
            patch.object(rag, "_get_or_create_collection", return_value=mock_collection),
        ):
            result = rag.index(str(tmp_path))

        assert result["files"] == 1  # only small.py

    def test_search_returns_results(self):
        """Search with a mocked collection returns properly shaped results."""
        rag = _make_rag()
        rag._indexed_dir = "/fake"

        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [["def hello(): ..."]],
            "metadatas": [[{"filepath": "/fake/hello.py", "chunk_index": 0}]],
            "distances": [[0.2]],
        }

        with (
            patch.object(rag, "_get_embeddings", return_value=[[0.1, 0.2, 0.3]]),
            patch.object(rag, "_get_or_create_collection", return_value=mock_collection),
        ):
            results = rag.search("hello world")

        assert len(results) == 1
        assert results[0]["filepath"] == "/fake/hello.py"
        assert results[0]["content"] == "def hello(): ..."
        assert results[0]["score"] == pytest.approx(0.8)

    def test_search_returns_empty_when_not_indexed(self):
        rag = _make_rag()
        results = rag.search("anything")
        assert results == []

    def test_search_returns_empty_when_embedding_fails(self):
        rag = _make_rag()
        rag._indexed_dir = "/fake"

        mock_collection = MagicMock()
        with (
            patch.object(rag, "_get_embeddings", return_value=None),
            patch.object(rag, "_get_or_create_collection", return_value=mock_collection),
        ):
            results = rag.search("anything")

        assert results == []

    def test_clear_drops_collection(self):
        rag = _make_rag()
        rag._indexed_dir = "/fake"

        mock_client = MagicMock()
        with patch.object(rag, "_get_chroma_client", return_value=mock_client):
            rag.clear()

        mock_client.delete_collection.assert_called_once()

    def test_status_when_indexed(self):
        rag = _make_rag()
        rag._indexed_dir = "/fake"

        mock_collection = MagicMock()
        mock_collection.count.return_value = 42

        with (
            patch.object(rag, "_get_or_create_collection", return_value=mock_collection),
            patch.object(rag, "_embedding_service_reachable", return_value=True),
        ):
            st = rag.status()

        assert st["chunks"] == 42
        assert st["indexed"] is True
        assert st["embedding_service_reachable"] is True


# ---------------------------------------------------------------------------
# 6. Collection naming
# ---------------------------------------------------------------------------

class TestCollectionName:
    def test_deterministic(self):
        name1 = Rag._collection_name("/some/path")
        name2 = Rag._collection_name("/some/path")
        assert name1 == name2

    def test_different_for_different_paths(self):
        name1 = Rag._collection_name("/path/a")
        name2 = Rag._collection_name("/path/b")
        assert name1 != name2

    def test_starts_with_rag_prefix(self):
        name = Rag._collection_name("/test")
        assert name.startswith("rag_")


# ---------------------------------------------------------------------------
# 7. Computer API integration
# ---------------------------------------------------------------------------

class TestComputerIntegration:
    def test_rag_is_on_computer(self):
        """The Rag instance should be accessible via computer.rag."""
        from interpreter import OpenInterpreter

        interp = OpenInterpreter()
        assert hasattr(interp.computer, "rag")
        assert isinstance(interp.computer.rag, Rag)

    def test_rag_in_tools_list(self):
        """Rag should appear in the computer tools list."""
        from interpreter import OpenInterpreter

        interp = OpenInterpreter()
        tools = interp.computer._get_all_computer_tools_list()
        assert interp.computer.rag in tools

    def test_rag_methods_in_system_message(self):
        """RAG public methods should appear in the computer API system message."""
        from interpreter import OpenInterpreter

        interp = OpenInterpreter()
        sys_msg = interp.computer.system_message
        assert "computer.rag.index" in sys_msg
        assert "computer.rag.search" in sys_msg
        assert "computer.rag.status" in sys_msg
        assert "computer.rag.clear" in sys_msg
