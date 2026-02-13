from rich.box import MINIMAL
from rich.console import Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
import json

from .base_block import BaseBlock


class CodeBlock(BaseBlock):
    """
    Code Blocks display code and outputs in different languages. You can also set the active_line!
    """

    def __init__(self, interpreter=None):
        super().__init__()

        self.type = "code"
        self.highlight_active_line = (
            interpreter.highlight_active_line if interpreter else None
        )

        # Define these for IDE auto-completion
        self.language = ""
        self.output = ""
        self.code = ""
        self.active_line = None
        self.margin_top = True

    def end(self):
        self.active_line = None
        self.refresh(cursor=False)
        super().end()

    def refresh(self, cursor=True):
        if not self.code and not self.output:
            return

        # Get code
        code = self.code

        # Create a table for the code
        code_table = Table(
            show_header=False, show_footer=False, box=None, padding=0, expand=True
        )
        code_table.add_column()

        # Add cursor only if active line highliting is true
        if cursor and (
            self.highlight_active_line
            if self.highlight_active_line is not None
            else True
        ):
            code += "●"

        # Add each line of code to the table
        code_lines = code.strip().split("\n")
        for i, line in enumerate(code_lines, start=1):
            if i == self.active_line and (
                self.highlight_active_line
                if self.highlight_active_line is not None
                else True
            ):
                # This is the active line, print it with a white background
                syntax = Syntax(
                    line, self.language, theme="bw", line_numbers=False, word_wrap=True
                )
                code_table.add_row(syntax, style="black on white")
            else:
                # This is not the active line, print it normally
                syntax = Syntax(
                    line,
                    self.language,
                    theme="material",
                    line_numbers=False,
                    word_wrap=True,
                )
                code_table.add_row(syntax)

        # Create a panel for the code
        language_label = self.language if self.language else "code"
        code_panel = Panel(
            code_table,
            box=MINIMAL,
            style="",
            title=f"▶ {language_label}",
            title_align="left",
        )

        # Create a panel for the output (if there is any)
        if self.output == "" or self.output == "None":
            output_panel = ""
        else:
            # Try to detect and format JSON output with better colors
            output_content = self.output
            try:
                # Check if output is JSON
                parsed_json = json.loads(self.output)
                # If it is valid JSON, format it nicely with syntax highlighting
                formatted_json = json.dumps(parsed_json, indent=2)
                json_syntax = Syntax(
                    formatted_json,
                    "json",
                    theme="material",
                    line_numbers=False,
                    word_wrap=True,
                )
                output_content = json_syntax
            except (json.JSONDecodeError, TypeError):
                # Not JSON, use as-is
                pass
            
            output_panel = Panel(
                output_content,
                box=MINIMAL,
                style="",
                title="📤 output",
                title_align="left",
            )

        # Create a group with the code table and output panel
        group_items = [code_panel, output_panel]
        if self.margin_top:
            # This adds some space at the top. Just looks good!
            group_items = [""] + group_items
        group = Group(*group_items)

        # Update the live display
        self.live.update(group)
        self.live.refresh()
