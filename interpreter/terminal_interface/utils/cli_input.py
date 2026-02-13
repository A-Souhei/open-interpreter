import os

try:
    from prompt_toolkit.application import Application
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.formatted_text import FormattedText
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout, HSplit, Window
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
    from prompt_toolkit.layout.margins import PromptMargin
    from prompt_toolkit.styles import Style as PTStyle
    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False


def _get_terminal_width():
    try:
        return os.get_terminal_size().columns
    except:
        return 80


def _print_info_line(model=""):
    """Print model (left) and current directory (right) above the top separator."""
    width = _get_terminal_width()
    cwd = os.getcwd()
    home = os.path.expanduser("~")
    if cwd.startswith(home):
        cwd = "~" + cwd[len(home):]

    left = model
    right = cwd
    # Ensure it fits: left + gap + right
    gap = width - len(left) - len(right)
    if gap < 1:
        # Truncate right side if too long
        available = width - len(left) - 1
        right = "…" + right[-(available - 1):] if available > 1 else ""
        gap = width - len(left) - len(right)

    line = left + " " * max(gap, 1) + right
    # dim gray color
    print(f"\033[90m{line}\033[0m")


def _print_separator():
    width = _get_terminal_width()
    print(f"\033[38;5;238m{'─' * width}\033[0m")


def _prompt_with_lines(prompt_text):
    """Custom prompt with separator line immediately below input."""
    kb = KeyBindings()

    @kb.add('enter')
    def _accept(event):
        event.app.exit(result=event.current_buffer.text)

    @kb.add('c-c')
    def _clear(event):
        event.current_buffer.reset()

    @kb.add('c-d')
    def _exit(event):
        os.system('cls' if os.name == 'nt' else 'clear')
        event.app.exit(exception=EOFError())

    buf = Buffer(name='input_buffer')

    prompt_margin = PromptMargin(lambda: [('class:prompt', prompt_text)])

    layout = Layout(
        HSplit([
            Window(
                content=BufferControl(buffer=buf),
                left_margins=[prompt_margin],
                wrap_lines=True,
                dont_extend_height=True,
            ),
            Window(
                content=FormattedTextControl(
                    lambda: [('class:separator', '─' * _get_terminal_width())]
                ),
                height=1,
            ),
        ])
    )

    style = PTStyle.from_dict({
        'prompt': '#af00ff',
        'separator': '#444444',
    })

    app = Application(layout=layout, key_bindings=kb, style=style)
    return app.run()


def cli_input(prompt_text: str = "", model: str = "") -> str:
    """
    Enhanced CLI input with visual separators
    """
    start_marker = '"""'
    end_marker = '"""'

    _print_info_line(model)
    _print_separator()

    if PROMPT_TOOLKIT_AVAILABLE:
        try:
            message = _prompt_with_lines(prompt_text)
        except (KeyboardInterrupt, EOFError):
            raise
    else:
        purple_prompt = f"\033[35m{prompt_text}\033[0m" if prompt_text else ""
        message = input(purple_prompt)
        _print_separator()

    # Multi-line input mode
    if start_marker in message:
        lines = [message]
        while True:
            line = input()
            lines.append(line)
            if end_marker in line:
                break
        result = "\n".join(lines)
    else:
        result = message

    return result


def simple_input(prompt_text: str = "", model: str = "") -> str:
    """
    Simple input with visual separators (for non-multiline mode)
    """
    _print_info_line(model)
    _print_separator()

    if PROMPT_TOOLKIT_AVAILABLE:
        try:
            result = _prompt_with_lines(prompt_text)
        except (KeyboardInterrupt, EOFError):
            raise
    else:
        purple_prompt = f"\033[35m{prompt_text}\033[0m" if prompt_text else ""
        result = input(purple_prompt)
        _print_separator()

    return result
