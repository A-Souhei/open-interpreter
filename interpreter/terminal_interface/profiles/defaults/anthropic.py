"""
This is an Open Interpreter profile. It configures Open Interpreter to use Anthropic's Claude Sonnet 4.5.

Requires ANTHROPIC_API_KEY in .env or environment.
"""

import os

from dotenv import load_dotenv

from interpreter import interpreter

load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise EnvironmentError(
        "ANTHROPIC_API_KEY not found. Set it in your .env file or environment."
    )

# LLM settings
interpreter.llm.model = "anthropic/claude-sonnet-4-5-20250929"
interpreter.llm.api_key = api_key
interpreter.llm.context_window = 200000
interpreter.llm.max_tokens = 4096

# Computer settings
interpreter.computer.import_computer_api = True

# Safety
interpreter.safe_mode = "ask"

# Misc settings
interpreter.auto_run = False

# Final message
interpreter.display_message(
    "➜ Model set to `claude-sonnet-4-5-20250929` (Anthropic)\n\n**Open Interpreter** will require approval before running code.\n\nUse `interpreter -y` to bypass this.\n\nPress `CTRL-C` to exit.\n"
)
