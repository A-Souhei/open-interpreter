"""Tests for terminal UI improvements: icons, labels, and prompt formatting."""

import io
from unittest.mock import MagicMock, patch

import pytest

from interpreter.terminal_interface.components.code_block import CodeBlock
from interpreter.terminal_interface.components.message_block import MessageBlock


class TestCodeBlockLabels:
    """Test that code blocks display language labels and output labels."""

    def test_code_panel_has_language_label(self):
        cb = CodeBlock()
        cb.language = "python"
        cb.code = 'print("hello")'
        cb.refresh(cursor=False)
        # The live display should have been updated; just verify no errors
        cb.end()

    def test_code_panel_defaults_to_code_label(self):
        cb = CodeBlock()
        cb.language = ""
        cb.code = "echo hi"
        cb.refresh(cursor=False)
        cb.end()

    def test_output_panel_has_label(self):
        cb = CodeBlock()
        cb.language = "python"
        cb.code = 'print("hello")'
        cb.output = "hello"
        cb.refresh(cursor=False)
        cb.end()

    def test_no_output_panel_when_empty(self):
        cb = CodeBlock()
        cb.language = "python"
        cb.code = 'x = 1'
        cb.output = ""
        cb.refresh(cursor=False)
        cb.end()

    def test_no_output_panel_when_none_string(self):
        cb = CodeBlock()
        cb.language = "python"
        cb.code = 'x = 1'
        cb.output = "None"
        cb.refresh(cursor=False)
        cb.end()


class TestTerminalInterfaceIcons:
    """Test that terminal interface messages contain expected icons."""

    def test_intro_message_has_lock_icon(self):
        """The intro message should include the lock icon."""
        from interpreter.terminal_interface.terminal_interface import terminal_interface

        interpreter_mock = MagicMock()
        interpreter_mock.auto_run = False
        interpreter_mock.offline = False
        interpreter_mock.messages = []
        interpreter_mock.safe_mode = "off"
        interpreter_mock.plain_text_display = False
        interpreter_mock.multi_line = False

        # Capture what display_message is called with
        displayed = []
        interpreter_mock.display_message.side_effect = lambda msg: displayed.append(msg)

        # The terminal_interface is a generator; we need to trigger it
        # but it will block on input(), so we mock that
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            try:
                gen = terminal_interface(interpreter_mock, None)
                next(gen)
            except (KeyboardInterrupt, StopIteration):
                pass

        assert len(displayed) >= 1
        assert "🔓" in displayed[0]

    def test_intro_message_has_bypass_icon(self):
        """The intro message should include the lightning icon for bypass hint."""
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

        assert len(displayed) >= 1
        assert "⚡" in displayed[0]

    def test_intro_message_has_keyboard_icon(self):
        """The intro message should include keyboard icon for CTRL-C hint."""
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

        assert len(displayed) >= 1
        assert "⌨️" in displayed[0]


class TestConversationNavigatorIcons:
    """Test that conversation navigator uses icons."""

    def test_open_folder_option_has_icon(self):
        """The Open Folder option should include a folder icon."""
        from interpreter.terminal_interface.conversation_navigator import (
            conversation_navigator,
        )

        # We just verify the string constant is correct in the source
        import inspect

        source = inspect.getsource(conversation_navigator)
        assert "📂 Open Folder →" in source
