"""
This is an Open Interpreter profile. It configures Open Interpreter to run `qwen2.5-coder:7b` using Ollama.

Requires OLLAMA_BASE_URL in .env or environment (defaults to http://localhost:11434).
"""

import os

from dotenv import load_dotenv

from interpreter import interpreter

load_dotenv()

ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
ollama_base_model = os.getenv("OLLAMA_BASE_MODEL", "ollama/qwen2.5-coder:7b")
ollama_safe_mode = os.getenv("OLLAMA_SAFE_MODE", "false").lower() == "true"

interpreter.system_message = """You are an AI assistant that writes markdown code snippets to answer the user's request. You speak very concisely and quickly, you say nothing irrelevant to the user's request. For example:

User: Open the chrome app.
Assistant: On it.
```python
import webbrowser
webbrowser.open('https://chrome.google.com')
```
User: The code you ran produced no output. Was this expected, or are we finished?
Assistant: No further action is required; the provided snippet opens Chrome.

Now, your turn:""".strip()

# Message templates
interpreter.code_output_template = '''I executed that code. This was the output: """{content}"""\n\nWhat does this output mean (I can't understand it, please help) / what code needs to be run next (if anything, or are we done)? I can't replace any placeholders.'''
interpreter.empty_code_output_template = "The code above was executed on my machine. It produced no text output. What's next (if anything, or are we done?)"
interpreter.code_output_sender = "user"

# LLM settings
interpreter.llm.model = ollama_base_model
interpreter.llm.api_base = ollama_base_url
interpreter.llm.supports_functions = False
interpreter.llm.execution_instructions = False
interpreter.llm.max_tokens = 1000
interpreter.llm.context_window = 7000
interpreter.llm.load()  # Loads Ollama models

# Computer settings
interpreter.computer.import_computer_api = False

# Safety
interpreter.safe_mode = "ask" if ollama_safe_mode else "off"

# Misc settings
interpreter.auto_run = False
interpreter.offline = True

# Final message
interpreter.display_message(
    "➜ Model set to `qwen2.5-coder:7b` (Ollama)\n\n**Open Interpreter** will require approval before running code.\n\nUse `interpreter -y` to bypass this.\n\nPress `CTRL-C` to exit.\n"
)
