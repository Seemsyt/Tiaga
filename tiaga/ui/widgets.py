"""
ui/widgets.py
-------------
Reusable Textual widgets that map 1-to-1 to the visual blocks in the
reference screenshots:

  • RainbowBorder      – the thin coloured gradient bar at the very top
  • ToolCallBlock      – collapsible "tool call" card (green outline)
  • AssistantMessage   – plain streaming text region
  • PlanPanel          – the "Plan" todo list panel
  • InputBar           – bottom input with hint labels
  • FooterBar          – key-binding strip at the bottom
  • DiffView           – right-hand diff panel (approval screen)
  • ApprovalSidebar    – left-hand Allow / Reject panel (approval screen)
"""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.markup import escape
from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Static

from .theme import TOOL_KIND_COLOR


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────

def _esc(s: str | None) -> str:
    return escape(str(s or ""))


# ─────────────────────────────────────────────────────────────────────────────
# RainbowBorder
# ─────────────────────────────────────────────────────────────────────────────

class RainbowBorder(Static):
    """
    The thin gradient bar at the very top of the screen (like Claude Code).
    Rendered as a Rich markup string of coloured block characters.
    """

    DEFAULT_CSS = """
    RainbowBorder {
        height: 1;
        padding: 0 0;
    }
    """

    _STOPS = [
        "#ff6b6b", "#ff8e53", "#ffd166", "#06d6a0",
        "#118ab2", "#7c3aed", "#c026d3",
    ]

    def on_mount(self) -> None:
        self._render_bar()

    def on_resize(self, _event: Any) -> None:
        self._render_bar()

    def _render_bar(self) -> None:
        w = self.size.width or 80
        stops = self._STOPS
        segment = max(1, w // len(stops))
        parts: list[str] = []
        for i, colour in enumerate(stops):
            count = segment if i < len(stops) - 1 else w - segment * (len(stops) - 1)
            parts.append(f"[on {colour}]{' ' * count}[/]")
        self.update("".join(parts))


# ─────────────────────────────────────────────────────────────────────────────
# ToolCallBlock
# ─────────────────────────────────────────────────────────────────────────────

class ToolCallBlock(Static):
    """
    A single tool-call card.  Can be in three states:
      running  – yellow/dim border, "running" subtitle
      success  – green border, ✓ checkmark
      error    – red border, ✗ mark
    """

    DEFAULT_CSS = """
    ToolCallBlock {
        margin: 1 0 0 0;
        border: tall #2a4a3a;
        background: #1a2820;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        call_id: str,
        tool_kind: str,
        name: str,
        arguments: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.call_id = call_id
        self.tool_kind = tool_kind
        self.tool_name = name
        self.arguments = arguments
        self._state: str = "running"   # "running" | "success" | "error"
        self._output_lines: list[Any] = []  # Rich renderables
        self._error: str | None = None

    # ── public API ────────────────────────────────────────────────────────────

    def mark_done(
        self,
        success: bool,
        output_renderables: list[Any],
        error: str | None = None,
    ) -> None:
        self._state = "success" if success else "error"
        self._output_lines = output_renderables
        self._error = error
        self._update_border()
        self._refresh_content()

    def update_arguments(self, arguments: dict[str, Any]) -> None:
        self.arguments = arguments
        self._refresh_content()

    # ── internal ──────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._refresh_content()

    def _update_border(self) -> None:
        colour = {
            "running": "#3a6a4a",
            "success": "#2a9a5a",
            "error":   "#9a3a3a",
        }[self._state]
        self.styles.border = ("tall", colour)

    def _header_text(self) -> Text:
        colour = TOOL_KIND_COLOR.get(self.tool_kind, "#a6e3a1")
        icon = {"running": "⬤", "success": "✓", "error": "✗"}[self._state]
        icon_style = {
            "running": "#f9e2af",
            "success": "#a6e3a1",
            "error":   "#f38ba8",
        }[self._state]
        t = Text()
        t.append(f"{icon} ", style=icon_style)
        t.append(self.tool_name, style=f"{colour} bold")
        t.append(f"  #{self.call_id[:8]}", style="#6c7086")
        return t

    def _args_text(self) -> Text:
        t = Text()
        for k, v in self.arguments.items():
            if isinstance(v, str) and k in {"content", "old_string", "new_string"}:
                lines = len(v.splitlines())
                size  = len(v.encode())
                v = f"{lines} lines · {size} bytes"
            val_str = str(v) if not isinstance(v, (dict, list)) else repr(v)
            t.append(f"  {k} ", style="#6c7086")
            t.append(val_str[:120], style="#cdd6f4")
            t.append("\n")
        return t

    def _subtitle_text(self) -> Text:
        label = {"running": "running", "success": "done", "error": "failed"}[self._state]
        style = {
            "running": "#6c7086",
            "success": "#a6e3a1",
            "error":   "#f38ba8",
        }[self._state]
        return Text(label, style=style, justify="right")

    def _refresh_content(self) -> None:
        parts: list[Any] = [
            self._header_text(),
        ]
        if self.arguments:
            parts.append(self._args_text())
        parts.extend(self._output_lines)
        parts.append(self._subtitle_text())
        self.update(Group(*parts))


# ─────────────────────────────────────────────────────────────────────────────
# AssistantMessage
# ─────────────────────────────────────────────────────────────────────────────

class AssistantMessage(Static):
    """
    Plain assistant prose.  Supports incremental append for streaming.
    """

    DEFAULT_CSS = """
    AssistantMessage {
        color: #cdd6f4;
        padding: 0 0 1 0;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._buffer = ""

    def append(self, delta: str) -> None:
        self._buffer += delta
        self.update(self._buffer)

    def set_text(self, text: str) -> None:
        self._buffer = text
        self.update(text)


# ─────────────────────────────────────────────────────────────────────────────
# PlanPanel
# ─────────────────────────────────────────────────────────────────────────────

class PlanPanel(Static):
    """
    The blue "Plan" panel that shows the agent's todo list with
    → active  ○ pending  ✓ done  markers.
    """

    DEFAULT_CSS = """
    PlanPanel {
        border: tall #3a3a6a;
        background: #1e1e35;
        margin: 1 0;
        padding: 0 1;
    }
    """

    # Each item: (label, status)  status ∈ {"pending","active","done"}
    items: reactive[list[tuple[str, str]]] = reactive(list, recompose=True)

    def __init__(self, items: list[tuple[str, str]], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._items = items

    def on_mount(self) -> None:
        self._render_plan()

    def set_items(self, items: list[tuple[str, str]]) -> None:
        self._items = items
        self._render_plan()

    def _render_plan(self) -> None:
        t = Text()
        t.append("  Plan\n", style="#89b4fa bold")
        icons = {"active": "➔ ", "pending": "○ ", "done": "✓ "}
        styles = {
            "active":  "#89b4fa bold",
            "pending": "#6c7086",
            "done":    "#45475a",
        }
        for label, status in self._items:
            icon  = icons.get(status, "  ")
            style = styles.get(status, "#cdd6f4")
            t.append(f"  {icon}{label}\n", style=style)
        self.update(t)


# ─────────────────────────────────────────────────────────────────────────────
# InputBar
# ─────────────────────────────────────────────────────────────────────────────

class InputBar(Widget):
    """
    Bottom input row — cursor, text field, hint badges.
    """

    DEFAULT_CSS = """
    InputBar {
        height: 3;
        border: tall #2a2e3e;
        background: #1e2030;
        padding: 0 1;
        layout: horizontal;
        align: left middle;
    }
    InputBar Static {
        color: #45475a;
        padding: 0 1;
        width: auto;
    }
    InputBar Input {
        background: transparent;
        border: none;
        padding: 0 1;
        color: #cdd6f4;
        width: 1fr;
    }
    InputBar Input:focus {
        border: none;
        background: transparent;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("❯", id="input-cursor")
        yield Input(
            placeholder="What would you like to do?",
            id="chat-input",
        )
        yield Static("[bold #f38ba8]![/] shell", id="hint-shell", markup=True)
        yield Static("[bold #cba6f7]/[/] commands", id="hint-cmds", markup=True)
        yield Static("[bold #89b4fa]@[/] files", id="hint-files", markup=True)

    def get_input_widget(self) -> Input:
        return self.query_one("#chat-input", Input)

    def on_mount(self) -> None:
        self._apply_responsive_hints(self.size.width)

    def on_resize(self, _event: Any) -> None:
        self._apply_responsive_hints(self.size.width)

    def _apply_responsive_hints(self, width: int) -> None:
        hints = [
            self.query_one("#hint-shell", Static),
            self.query_one("#hint-cmds", Static),
            self.query_one("#hint-files", Static),
        ]
        if width < 70:
            for hint in hints:
                hint.styles.display = "none"
        elif width < 90:
            hints[0].styles.display = "none"
            hints[1].styles.display = "none"
            hints[2].styles.display = "block"
        elif width < 110:
            hints[0].styles.display = "none"
            hints[1].styles.display = "block"
            hints[2].styles.display = "block"
        else:
            for hint in hints:
                hint.styles.display = "block"


# ─────────────────────────────────────────────────────────────────────────────
# FooterBar
# ─────────────────────────────────────────────────────────────────────────────

class FooterBar(Static):
    """
    One-line keybinding strip at the very bottom.
    """

    DEFAULT_CSS = """
    FooterBar {
        height: 1;
        background: #181825;
        padding: 0 1;
        color: #6c7086;
    }
    """

    _BINDINGS: list[tuple[str, str]] = [
        ("^f", "Focus"),
        ("⏎", "Send"),
        ("esc", "Dismiss"),
        ("alt+↑ alt+↓", "Cursor"),
        ("^o", "Modes"),
        ("^b", "Sidebar"),
        ("f1", "Help"),
        ("f2", "Settings"),
        ("^p", "palette"),
    ]

    def on_mount(self) -> None:
        self._render_for_width(self.size.width)

    def on_resize(self, _event: Any) -> None:
        self._render_for_width(self.size.width)

    def _render_for_width(self, width: int) -> None:
        parts: list[str] = []
        current_len = 0
        for key, label in self._BINDINGS:
            chunk = f"[bold #89b4fa]{escape(key)}[/] [#6c7086]{escape(label)}[/]"
            plain_len = len(f"{key} {label}") + 2
            if current_len + plain_len > max(10, width - 6):
                break
            parts.append(chunk)
            current_len += plain_len
        self.update("  " + "  ".join(parts))


# ─────────────────────────────────────────────────────────────────────────────
# ApprovalSidebar
# ─────────────────────────────────────────────────────────────────────────────

class ApprovalSidebar(Static):
    """
    Left panel on the diff/approval screen.
    Shows:  ❯ A  Always Allow  /  a Allow  /  r Reject
    and a file list below.
    """

    DEFAULT_CSS = """
    ApprovalSidebar {
        width: 20;
        border-right: tall #2a2e3e;
        background: #1a1e2e;
        padding: 1 1;
    }
    """

    def __init__(self, filenames: list[str], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._filenames = filenames
        self._selected = 0   # 0=AlwaysAllow, 1=Allow, 2=Reject

    def on_mount(self) -> None:
        self._render()

    def _render(self) -> None:
        t = Text()
        options = [
            ("A", "Always Allow"),
            ("a", "Allow"),
            ("r", "Reject"),
        ]
        for i, (key, label) in enumerate(options):
            if i == self._selected:
                t.append(f" ❯ ", style="#cba6f7 bold")
                t.append(f"{key}  ", style="#cba6f7 bold")
                t.append(f"{label}\n", style="#cba6f7 bold")
            else:
                t.append(f"   {key}  ", style="#585b70")
                t.append(f"{label}\n", style="#6c7086")
        t.append("\n")
        for fname in self._filenames:
            t.append(f"  📄 {fname}\n", style="#6c7086")
        self.update(t)

    def select_next(self) -> None:
        self._selected = (self._selected + 1) % 3
        self._render()

    def select_prev(self) -> None:
        self._selected = (self._selected - 1) % 3
        self._render()

    @property
    def selected_action(self) -> str:
        return ["always_allow", "allow", "reject"][self._selected]


# ─────────────────────────────────────────────────────────────────────────────
# DiffView
# ─────────────────────────────────────────────────────────────────────────────

class DiffView(Static):
    """
    Right-hand panel — shows a syntax-highlighted diff with line numbers.
    """

    DEFAULT_CSS = """
    DiffView {
        width: 1fr;
        overflow: auto auto;
        padding: 0 0;
    }
    """

    def __init__(
        self,
        filename: str,
        content: str,
        added: int = 0,
        removed: int = 0,
        language: str = "html",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._filename = filename
        self._content  = content
        self._added    = added
        self._removed  = removed
        self._language = language

    def on_mount(self) -> None:
        self._render()

    def _render(self) -> None:
        header = Text()
        header.append(f"  {self._filename}", style="#cdd6f4")
        header.append("  (", style="#6c7086")
        header.append(f"+{self._added}", style="#a6e3a1 bold")
        header.append(", ", style="#6c7086")
        header.append(f"-{self._removed}", style="#f38ba8 bold")
        header.append(")", style="#6c7086")
        header.append("\n\n")

        syntax = Syntax(
            self._content,
            self._language,
            theme="monokai",
            line_numbers=True,
            word_wrap=False,
        )
        self.update(Group(header, syntax))
