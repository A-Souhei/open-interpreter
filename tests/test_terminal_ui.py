"""Tests for terminal UI improvements: icons, labels, and prompt formatting."""

import io
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from rich.console import Console

from interpreter.terminal_interface.components.code_block import CodeBlock
from interpreter.terminal_interface.components.message_block import MessageBlock


class TestCodeBlockLabels:
    """Test that code blocks display language labels and output labels."""

    def _render_code_block(self, language, code, output=""):
        """Helper to render a code block and capture the Rich Group output."""
        cb = CodeBlock()
        cb.live.stop()  # Stop the default live display
        cb.live = MagicMock()  # Mock it so we can capture updates
        cb.language = language
        cb.code = code
        cb.output = output

        captured_group = {}

        def capture_update(group):
            captured_group["group"] = group

        cb.live.update = capture_update
        cb.live.refresh = MagicMock()
        cb.refresh(cursor=False)
        return captured_group.get("group")

    def test_code_panel_has_language_label(self):
        group = self._render_code_block("python", 'print("hello")')
        renderables = list(group.renderables)
        panels_with_title = [r for r in renderables if hasattr(r, "title") and r.title]
        assert any("python" in str(p.title) for p in panels_with_title)
        assert any("\u23f5" in str(p.title) for p in panels_with_title)

    def test_code_panel_defaults_to_code_label(self):
        group = self._render_code_block("", "echo hi")
        renderables = list(group.renderables)
        panels_with_title = [r for r in renderables if hasattr(r, "title") and r.title]
        assert any("code" in str(p.title) for p in panels_with_title)

    def test_output_panel_has_label(self):
        group = self._render_code_block("python", 'print("hello")', output="hello")
        renderables = list(group.renderables)
        panels_with_title = [r for r in renderables if hasattr(r, "title") and r.title]
        titles = [str(p.title) for p in panels_with_title]
        assert any("\U0001f4ce" in t and "output" in t for t in titles)

    def test_no_output_panel_when_empty(self):
        group = self._render_code_block("python", "x = 1", output="")
        renderables = list(group.renderables)
        panels_with_title = [r for r in renderables if hasattr(r, "title") and r.title]
        titles = [str(p.title) for p in panels_with_title]
        assert not any("\U0001f4ce" in t for t in titles)

    def test_no_output_panel_when_none_string(self):
        group = self._render_code_block("python", "x = 1", output="None")
        renderables = list(group.renderables)
        panels_with_title = [r for r in renderables if hasattr(r, "title") and r.title]
        titles = [str(p.title) for p in panels_with_title]
        assert not any("\U0001f4ce" in t for t in titles)


class TestTerminalInterfaceIcons:
    """Test that terminal interface messages contain expected icons."""

    def _get_displayed_intro(self):
        """Helper to capture the intro message from terminal_interface."""
        from interpreter.terminal_interface.terminal_interface import terminal_interface

        interpreter_mock = MagicMock()
        interpreter_mock.auto_run = False
        interpreter_mock.offline = False
        interpreter_mock.messages = []
        interpreter_mock.safe_mode = "off"
        interpreter_mock.plain_text_display = False
        interpreter_mock.multi_line = False

        displayed = []
        interpreter_mock.display_message.side_effect = lambda msg: displayed.append(msg)

        with patch("builtins.input", side_effect=KeyboardInterrupt):
            try:
                gen = terminal_interface(interpreter_mock, None)
                next(gen)
            except (KeyboardInterrupt, StopIteration):
                pass

        return displayed

    def test_intro_message_has_lock_icon(self):
        displayed = self._get_displayed_intro()
        assert len(displayed) >= 1
        assert "\U0001f513" in displayed[0]

    def test_intro_message_has_bypass_icon(self):
        displayed = self._get_displayed_intro()
        assert len(displayed) >= 1
        assert "\u26a1" in displayed[0]

    def test_intro_message_has_keyboard_icon(self):
        displayed = self._get_displayed_intro()
        assert len(displayed) >= 1
        assert "\u2328" in displayed[0]


class TestConversationNavigatorIcons:
    """Test that conversation navigator uses icons in the Open Folder choice."""

    def test_open_folder_option_has_icon(self):
        from interpreter.terminal_interface.conversation_navigator import (
            conversation_navigator,
        )

        interpreter_mock = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            fake_conv = os.path.join(tmpdir, "Hello__Jan_1.json")
            with open(fake_conv, "w") as f:
                json.dump([], f)

            with patch(
                "interpreter.terminal_interface.conversation_navigator.get_storage_path",
                return_value=tmpdir,
            ), patch(
                "interpreter.terminal_interface.conversation_navigator.inquirer.List",
            ) as mock_list, patch(
                "interpreter.terminal_interface.conversation_navigator.inquirer.prompt",
                return_value=None,
            ):
                conversation_navigator(interpreter_mock)

            call_kwargs = mock_list.call_args
            choices = call_kwargs.kwargs.get(
                "choices", call_kwargs[1].get("choices", [])
            )
            assert any(
                "\U0001f4c2" in str(c) for c in choices
            ), f"Expected folder icon in choices: {choices}"
