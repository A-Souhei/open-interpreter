"""
This is an Open Interpreter profile for RAG (Retrieval-Augmented Generation).

It indexes the current working directory on startup so the LLM can
semantically search the codebase.

Requires:
  - EMBEDDING_SERVICE_URL (default http://localhost:8100)
  - An API key for your chosen LLM in .env or environment
  - pip install open-interpreter[rag]
"""

import os

from dotenv import load_dotenv

from interpreter import interpreter

load_dotenv()

# LLM selection — honour OI_MODEL or fall back to Anthropic Claude
model = os.getenv("OI_MODEL", "anthropic/claude-sonnet-4-5-20250929")
interpreter.llm.model = model
interpreter.llm.context_window = 200000
interpreter.llm.max_tokens = 4096

# Computer settings
interpreter.computer.import_computer_api = True

# RAG configuration
embedding_url = os.getenv("EMBEDDING_SERVICE_URL", "http://localhost:8100")
interpreter.computer.rag.embedding_service_url = embedding_url

# Safety
interpreter.safe_mode = "ask"

# Misc settings
interpreter.auto_run = False

# Custom instructions so the LLM knows about RAG
interpreter.custom_instructions = """
You have access to a RAG (Retrieval-Augmented Generation) system via computer.rag.
Use computer.rag.search(query) to find relevant code snippets from the indexed codebase.
Use computer.rag.index(path) to re-index a directory.
Use computer.rag.status() to check indexing status.
Use computer.rag.clear() to drop the index.
Relevant codebase context is automatically injected into your system message when available.
""".strip()

# Auto-index the current working directory on startup
interpreter.display_message(f"➜ Model set to `{model}`\n")
interpreter.display_message("⏳ Indexing current directory for RAG...\n")

try:
    result = interpreter.computer.rag.index(os.getcwd())
    interpreter.display_message(
        f"✅ RAG ready: {result['files']} files, {result['chunks']} chunks\n"
    )
except Exception as e:
    interpreter.display_message(
        f"⚠️  RAG indexing failed ({e}). The interpreter will work without RAG context.\n"
    )

interpreter.display_message(
    "**Open Interpreter** will require approval before running code.\n\nUse `interpreter -y` to bypass this.\n\nPress `CTRL-C` to exit.\n"
)
