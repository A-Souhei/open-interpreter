"""
This is an Open Interpreter profile. It configures Open Interpreter to use OpenAI's GPT-4o.

Requires OPENAI_API_KEY in .env or environment.
"""

import os

from dotenv import load_dotenv

from interpreter import interpreter

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise EnvironmentError(
        "OPENAI_API_KEY not found. Set it in your .env file or environment."
    )

# LLM settings
interpreter.llm.model = "gpt-4o"
interpreter.llm.api_key = api_key
interpreter.llm.context_window = 128000
interpreter.llm.max_tokens = 4096

# Computer settings
interpreter.computer.import_computer_api = True

# Safety
interpreter.safe_mode = "ask"

# Misc settings
interpreter.auto_run = False

# Final message
interpreter.display_message(
    "➜ Model set to `gpt-4o` (OpenAI)\n\n**Open Interpreter** will require approval before running code.\n\nUse `interpreter -y` to bypass this.\n\nPress `CTRL-C` to exit.\n"
)
