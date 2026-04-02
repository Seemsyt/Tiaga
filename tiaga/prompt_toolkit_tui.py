"""
Tiaga TUI — Claude Code-style terminal interface.

Design principles:
- Full-screen, panel-based layout (sidebar + main)
- Rich markdown rendering in transcript
- Inline tool call / result display with collapsible hints
- Persistent status bar with token/model info
- Keyboard-first, no decorative noise
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from prompt_toolkit.application import Application, get_app
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import StyleAndTextTuples, to_formatted_text, HTML
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.layout import (
    ConditionalContainer,
    HSplit,
    Layout,
    VSplit,
    Window,
    FloatContainer,
    Float,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import D
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea, SearchToolbar

from .chat_engine import ChatEngine
from .utils import (
    DB_PATH,
    _auto_name,
    _slug,
    ensure_api_key,
    list_threads,
    pick_session,
)


# ── Palette ──────────────────────────────────────────────────────────────────
# Matches Claude Code's actual dark-terminal palette

STYLE = Style.from_dict(
    {
        # chrome
        "chrome":              "bg:#1a1a1a #3a3a3a",
        "sidebar":             "bg:#111111",
        "sidebar.border":      "#2a2a2a",
        "main":                "bg:#0d0d0d",
        "divider":             "#222222",

        # sidebar items
        "sidebar.header":      "#666666",
        "sidebar.item":        "#888888",
        "sidebar.item.active": "bg:#1e1e1e #e8e8e8 bold",
        "sidebar.item.hover":  "bg:#181818 #bbbbbb",

        # transcript
        "role.user":           "#7c8cf8 bold",         # indigo — same shade Claude Code uses
        "role.assistant":      "#a8d8a8 bold",          # soft green
        "role.tool":           "#f4a261 bold",          # warm amber for tool calls
        "role.result":         "#888888",
        "role.meta":           "#555555 italic",

        "msg.user":            "#e0e0e0",
        "msg.assistant":       "#cccccc",
        "msg.tool":            "#c9a96e",
        "msg.result":          "#666666",
        "msg.meta":            "#444444",

        "msg.code":            "#98c379",               # green for inline code  ` `
        "msg.heading":         "#e8e8e8 bold",
        "msg.bullet":          "#888888",

        # input area
        "input.border":        "#2a2a2a",
        "input.prompt":        "#444444",
        "input.text":          "#e0e0e0",
        "input.placeholder":   "#3a3a3a",

        # status bar (bottom)
        "status":              "bg:#111111 #555555",
        "status.key":          "#888888 bold",
        "status.sep":          "#333333",
        "status.model":        "#666666",
        "status.session":      "#7c8cf8",
        "status.ready":        "#a8d8a8",
        "status.busy":         "#f4a261",
        "status.error":        "#e06c75",

        # top bar
        "topbar":              "bg:#111111",
        "topbar.title":        "#e8e8e8 bold",
        "topbar.sub":          "#555555",
        "topbar.cwd":          "#666666",
        "topbar.sep":          "#333333",

        # tool/result boxes
        "tool.box":            "bg:#141414",
        "tool.label":          "#f4a261",
        "tool.content":        "#888888",
        "result.label":        "#555555",
        "result.content":      "#666666",
    }
)


# ── Data ─────────────────────────────────────────────────────────────────────

@dataclass
class Block:
    """One rendered unit in the transcript."""
    role: str       # user | assistant | tool | result | meta
    lines: list[str] = field(default_factory=list)
    tool_name: str = ""
    collapsed: bool = False


def _parse_message_content(content: object) -> list[str]:
    if isinstance(content, str):
        return content.splitlines() or [""]
    if isinstance(content, list):
        out: list[str] = []
        for item in content:
            if isinstance(item, str):
                out.extend(item.splitlines())
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content") or str(item)
                out.extend(str(text).splitlines())
            else:
                out.extend(str(item).splitlines())
        return out or [""]
    return str(content).splitlines() or [""]


def _load_history(messages: list[BaseMessage]) -> list[Block]:
    blocks: list[Block] = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            blocks.append(Block("user", _parse_message_content(msg.content)))
        elif isinstance(msg, AIMessage):
            if getattr(msg, "tool_calls", None):
                continue
            lines = _parse_message_content(msg.content)
            if any(l.strip() for l in lines):
                blocks.append(Block("assistant", lines))
    return blocks


# ── Rendering ────────────────────────────────────────────────────────────────

_ROLE_LABELS = {
    "user":      "You",
    "assistant": "Tiaga",
    "tool":      "Tool",
    "result":    "  └─",
    "meta":      "Info",
}

_ROLE_STYLE = {
    "user":      "class:role.user",
    "assistant": "class:role.assistant",
    "tool":      "class:role.tool",
    "result":    "class:role.result",
    "meta":      "class:role.meta",
}

_MSG_STYLE = {
    "user":      "class:msg.user",
    "assistant": "class:msg.assistant",
    "tool":      "class:msg.tool",
    "result":    "class:msg.result",
    "meta":      "class:msg.meta",
}


def _render_line(line: str, role: str) -> StyleAndTextTuples:
    """Very lightweight inline Markdown: `code`, **bold**, # heading, - bullet."""
    style = _MSG_STYLE.get(role, "class:msg.assistant")
    if role in ("tool", "result", "meta"):
        return [(style, line)]

    frags: StyleAndTextTuples = []
    if line.startswith("# "):
        frags.append(("class:msg.heading", line[2:]))
        return frags
    if line.startswith("## "):
        frags.append(("class:msg.heading", line[3:]))
        return frags
    if line.startswith("- ") or line.startswith("* "):
        frags.append(("class:msg.bullet", "  • "))
        line = line[2:]

    # inline `code`
    i = 0
    while i < len(line):
        if line[i] == "`":
            end = line.find("`", i + 1)
            if end != -1:
                frags.append((style, line[:i]))
                frags.append(("class:msg.code", line[i + 1:end]))
                line = line[end + 1:]
                i = 0
                continue
        i += 1
    frags.append((style, line))
    return frags


def _blocks_to_formatted(blocks: list[Block], width: int = 80) -> str:
    """Render blocks to a plain string for the TextArea."""
    # We use plain text for the TextArea; formatting is handled by the role labels.
    rows: list[str] = []
    for block in blocks:
        label = _ROLE_LABELS.get(block.role, block.role)
        if block.role == "tool" and block.tool_name:
            label_line = f"{label}  {block.tool_name}"
        else:
            label_line = label

        rows.append(label_line)
        indent = "  "
        for line in block.lines:
            if line.startswith("- ") or line.startswith("* "):
                rows.append(f"{indent}• {line[2:]}")
            elif line.startswith("# "):
                rows.append(f"{indent}{line[2:]}")
            else:
                rows.append(f"{indent}{line}")
        rows.append("")
    return "\n".join(rows)


# ── Session Picker ────────────────────────────────────────────────────────────

def select_session_tui() -> str:
    """
    Full-screen session picker.
    Layout: left panel (sessions) | right panel (preview / keybinds)
    """
    try:
        threads = asyncio.run(list_threads(DB_PATH))
        selected = {"index": 0}
        result = {"value": None}
        show_input = {"v": False}

        input_field = TextArea(
            multiline=False,
            style="class:input.text",
            height=1,
        )

        def _sessions_text() -> StyleAndTextTuples:
            frags: StyleAndTextTuples = [
                ("class:topbar.title", "  Sessions\n"),
                ("class:topbar.sub",  "  ─────────────────────\n"),
            ]
            if not threads:
                frags.append(("class:sidebar.item", "  No saved sessions\n"))
            for i, t in enumerate(threads):
                if i == selected["index"]:
                    frags.append(("class:sidebar.item.active", f"  ❯ {t}\n"))
                else:
                    frags.append(("class:sidebar.item", f"    {t}\n"))
            return frags

        def _help_text() -> StyleAndTextTuples:
            frags: StyleAndTextTuples = [
                ("class:topbar.title", "  Keybinds\n"),
                ("class:topbar.sub",   "  ─────────────────────\n"),
                ("class:status.key",   "  ↑ ↓  k j"),
                ("class:status",       "   navigate\n"),
                ("class:status.key",   "  Enter   "),
                ("class:status",       "   open session\n"),
                ("class:status.key",   "  n        "),
                ("class:status",       "   new named session\n"),
                ("class:status.key",   "  a        "),
                ("class:status",       "   auto-named session\n"),
                ("class:status.key",   "  q  Ctrl+C"),
                ("class:status",       "   quit\n"),
                ("class:topbar.sub",   "\n  ─────────────────────\n"),
                ("class:topbar.sub",   "  Tiaga — your AI coding\n"),
                ("class:topbar.sub",   "  companion in the terminal\n"),
            ]
            return frags

        left = Window(
            content=FormattedTextControl(_sessions_text, focusable=True, show_cursor=False),
            style="class:sidebar",
            width=D(preferred=32, max=40),
        )
        right = Window(
            content=FormattedTextControl(_help_text, focusable=False),
            style="class:main",
        )
        vdiv = Window(width=1, char="│", style="class:divider")

        header = Window(
            content=FormattedTextControl(lambda: [
                ("class:topbar.title", "  tiaga  "),
                ("class:topbar.sep",   "│  "),
                ("class:topbar.sub",   "select or create a session"),
            ]),
            height=1,
            style="class:topbar",
        )
        hdiv_top = Window(height=1, char="─", style="class:divider")

        input_label = Window(
            content=FormattedTextControl(lambda: [
                ("class:input.prompt", "  session name › "),
            ]),
            height=1,
            width=D(preferred=18),
            dont_extend_width=True,
        )
        input_row = ConditionalContainer(
            content=VSplit([input_label, input_field]),
            filter=Condition(lambda: show_input["v"]),
        )
        empty_row = ConditionalContainer(
            content=Window(height=1, style="class:sidebar"),
            filter=Condition(lambda: not show_input["v"]),
        )

        status_bar = Window(
            content=FormattedTextControl(lambda: [
                ("class:status", "  Press "),
                ("class:status.key", "Enter"),
                ("class:status", " to resume  "),
                ("class:status.key", "n"),
                ("class:status", " new  "),
                ("class:status.key", "a"),
                ("class:status", " auto  "),
                ("class:status.key", "q"),
                ("class:status", " quit  "),
            ]),
            height=1,
            style="class:status",
        )

        root = HSplit([
            header,
            hdiv_top,
            VSplit([left, vdiv, right]),
            Window(height=1, char="─", style="class:divider"),
            input_row,
            empty_row,
            status_bar,
        ])

        kb = KeyBindings()

        @kb.add("up")
        @kb.add("k")
        def _up(event):
            if not show_input["v"]:
                selected["index"] = max(0, selected["index"] - 1)
                event.app.invalidate()

        @kb.add("down")
        @kb.add("j")
        def _down(event):
            if not show_input["v"]:
                selected["index"] = min(max(0, len(threads) - 1), selected["index"] + 1)
                event.app.invalidate()

        @kb.add("enter", eager=True)
        def _enter(event):
            if show_input["v"]:
                raw = input_field.text.strip()
                result["value"] = _slug(raw) if raw else _auto_name()
                event.app.exit()
                return
            if threads:
                result["value"] = threads[selected["index"]]
            else:
                result["value"] = _auto_name()
            event.app.exit()

        @kb.add("n")
        def _new(event):
            show_input["v"] = True
            event.app.layout.focus(input_field)
            event.app.invalidate()

        @kb.add("escape")
        def _esc(event):
            if show_input["v"]:
                show_input["v"] = False
                event.app.layout.focus(left)
                event.app.invalidate()

        @kb.add("a")
        def _auto(event):
            result["value"] = _auto_name()
            event.app.exit()

        @kb.add("q")
        @kb.add("c-c", eager=True)
        @kb.add("c-d", eager=True)
        def _quit(event):
            event.app.exit(exception=KeyboardInterrupt)

        app = Application(
            layout=Layout(root, focused_element=left),
            key_bindings=kb,
            style=STYLE,
            full_screen=True,
            mouse_support=True,
        )
        app.run()
        return result["value"] or _auto_name()

    except Exception:
        return pick_session()


# ── Main TUI ─────────────────────────────────────────────────────────────────

class TiagaTUI:
    """
    Three-panel layout:
      ┌─ header ──────────────────────────────────────────────────────────┐
      │ sidebar (sessions) │ transcript                                    │
      │                    │                                               │
      ├────────────────────┴──────────────────────────────────────────────┤
      │ input area                                                        │
      ├───────────────────────────────────────────────────────────────────┤
      │ status bar                                                        │
      └───────────────────────────────────────────────────────────────────┘
    """

    def __init__(self, thread_id: str, history: Optional[list[BaseMessage]] = None, all_threads: Optional[list[str]] = None):
        self.thread_id = thread_id
        self.cwd = str(Path.cwd())
        self.engine = ChatEngine()
        self.all_threads: list[str] = all_threads or [thread_id]
        self.sidebar_visible = {"v": True}
        self.selected_thread = {"index": self._thread_index()}

        loaded = _load_history(history or [])
        intro_lines = [f"session  {self.thread_id}"]
        if loaded:
            intro_lines.append(f"{len(loaded)} messages loaded")
        intro_lines.append("enter sends  ·  esc+enter newline  ·  ctrl+n new session")

        self.blocks: list[Block] = [Block("meta", intro_lines), *loaded]
        self.pending: Optional[Block] = None
        self.is_busy = False
        self.auto_scroll = True
        self.status = "ready"
        self.status_style = "status.ready"
        self.input_line_count = 1

        # ── Widgets ──
        self.transcript_area = TextArea(
            text=self._render_transcript(),
            read_only=True,
            scrollbar=True,
            focusable=False,
            wrap_lines=True,
            style="class:main",
        )
        self.input_area = TextArea(
            multiline=True,
            wrap_lines=True,
            style="class:input.text",
            height=D(min=3, max=12),
        )

        # Sidebar session list
        self.sidebar_win = Window(
            content=FormattedTextControl(self._render_sidebar, focusable=False, show_cursor=False),
            style="class:sidebar",
            width=D(preferred=28, max=36),
        )
        self.vdiv = Window(width=1, char="│", style="class:divider")

        self.header_win = Window(
            content=FormattedTextControl(self._render_header),
            height=1,
            style="class:topbar",
        )
        self.status_win = Window(
            content=FormattedTextControl(self._render_status),
            height=1,
            style="class:status",
        )

        sidebar_panel = ConditionalContainer(
            content=VSplit([self.sidebar_win, self.vdiv]),
            filter=Condition(lambda: self.sidebar_visible["v"]),
        )

        content_row = VSplit([sidebar_panel, self.transcript_area])

        root = HSplit([
            self.header_win,
            Window(height=1, char="─", style="class:divider"),
            content_row,
            Window(height=1, char="─", style="class:divider"),
            self.input_area,
            self.status_win,
        ])

        self.application = Application(
            layout=Layout(root, focused_element=self.input_area),
            key_bindings=self._bindings(),
            style=STYLE,
            full_screen=True,
            mouse_support=True,
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _thread_index(self) -> int:
        try:
            return self.all_threads.index(self.thread_id)
        except ValueError:
            return 0

    def _render_sidebar(self) -> StyleAndTextTuples:
        frags: StyleAndTextTuples = [
            ("class:sidebar.header", "  Sessions\n"),
        ]
        for i, t in enumerate(self.all_threads):
            if t == self.thread_id:
                frags.append(("class:sidebar.item.active", f"  ❯ {t[:22]}\n"))
            else:
                frags.append(("class:sidebar.item", f"    {t[:22]}\n"))
        return frags

    def _render_header(self) -> StyleAndTextTuples:
        return [
            ("class:topbar.title", "  tiaga"),
            ("class:topbar.sep",   "  │  "),
            ("class:status.session", self.thread_id),
            ("class:topbar.sep",   "  │  "),
            ("class:topbar.cwd",   self.cwd),
        ]

    def _render_status(self) -> StyleAndTextTuples:
        return [
            ("class:status.key", " Enter"),
            ("class:status",     " send  "),
            ("class:status.key", "Esc+Enter"),
            ("class:status",     " newline  "),
            ("class:status.key", "Ctrl+N"),
            ("class:status",     " new  "),
            ("class:status.key", "Ctrl+B"),
            ("class:status",     " sidebar  "),
            ("class:status.key", "End"),
            ("class:status",     " scroll  "),
            ("class:status.sep", "   ─   "),
            (f"class:{self.status_style}", self.status),
        ]

    def _render_transcript(self) -> str:
        return _blocks_to_formatted(self.blocks)

    # ── Key bindings ──────────────────────────────────────────────────────────

    def _bindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("c-c", eager=True)
        @kb.add("c-d", eager=True)
        def _exit(event):
            event.app.exit()

        @kb.add("enter")
        def _send(event):
            if not self.is_busy:
                self._submit()

        @kb.add("escape", "enter")
        def _newline(event):
            event.current_buffer.insert_text("\n")

        @kb.add("c-n")
        def _new_session(event):
            if self.is_busy:
                return
            new_id = _auto_name()
            self.all_threads.insert(0, new_id)
            self._switch_thread(new_id, history=[])

        @kb.add("c-b")
        def _toggle_sidebar(event):
            self.sidebar_visible["v"] = not self.sidebar_visible["v"]
            event.app.invalidate()

        @kb.add("pageup")
        def _scroll_up(event):
            self.auto_scroll = False
            self.transcript_area.buffer.cursor_up(count=12)
            event.app.invalidate()

        @kb.add("pagedown")
        @kb.add("end")
        def _scroll_down(event):
            self.auto_scroll = True
            self._go_to_bottom()
            event.app.invalidate()

        return kb

    # ── Logic ─────────────────────────────────────────────────────────────────

    def _switch_thread(self, thread_id: str, history: list[BaseMessage]) -> None:
        self.thread_id = thread_id
        loaded = _load_history(history)
        self.blocks = [
            Block("meta", [f"session  {thread_id}", f"{len(loaded)} messages loaded" if loaded else "new session"]),
            *loaded,
        ]
        self.pending = None
        self.auto_scroll = True
        self.status = "ready"
        self.status_style = "status.ready"
        self.input_area.text = ""
        self._refresh()

    def _submit(self) -> None:
        text = self.input_area.text.strip()
        if not text:
            return
        if text.lower() in {"exit", "quit", "bye", "/exit", "/quit"}:
            self.application.exit()
            return

        self.input_area.text = ""
        self.blocks.append(Block("user", text.splitlines()))
        self.pending = Block("assistant", [""])
        self.blocks.append(self.pending)
        self.is_busy = True
        self.status = "thinking…"
        self.status_style = "status.busy"
        self._refresh()
        self.application.create_background_task(self._stream(text))

    async def _stream(self, user_input: str) -> None:
        try:
            async for event in self.engine.stream_turn(user_input, self.thread_id):
                kind = event["event"]

                if kind == "on_tool_start":
                    tool_input = event["data"].get("input", {})
                    hint = ""
                    if isinstance(tool_input, dict):
                        v = next(iter(tool_input.values()), "")
                        if v:
                            hint = str(v)[:80]
                    name = event.get("name", "tool")
                    self.status = f"running {name}"
                    block = Block("tool", [hint] if hint else ["…"], tool_name=name)
                    self.blocks.append(block)
                    self._refresh()

                elif kind == "on_tool_end":
                    output = str(event["data"].get("output", "")).replace("\n", " ")
                    preview = output[:120] + ("…" if len(output) > 120 else "")
                    self.blocks.append(Block("result", [preview or "done"]))
                    self.status = "thinking…"
                    self._refresh()

                elif kind == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk and chunk.content and self.pending is not None:
                        self._append_chunk(chunk.content)
                        self._refresh()

            if self.pending is not None and self.pending.lines == [""]:
                self.pending.lines = ["…"]

        except Exception as exc:
            self.status = f"error"
            self.status_style = "status.error"
            self.blocks.append(Block("meta", [f"error: {exc}"]))
        finally:
            self.pending = None
            if self.status_style != "status.error":
                self.status = "ready"
                self.status_style = "status.ready"
            self.is_busy = False
            self._refresh()

    def _append_chunk(self, chunk: str) -> None:
        if self.pending is None:
            return
        parts = chunk.split("\n")
        self.pending.lines[-1] += parts[0]
        for p in parts[1:]:
            self.pending.lines.append(p)

    def _refresh(self) -> None:
        self.transcript_area.text = self._render_transcript()
        if self.auto_scroll:
            self._go_to_bottom()
        try:
            get_app().invalidate()
        except Exception:
            pass

    def _go_to_bottom(self) -> None:
        buf = self.transcript_area.buffer
        buf.cursor_position = len(buf.text)

    def run(self) -> None:
        self.application.run()


# ── Entry points ──────────────────────────────────────────────────────────────

def run_tui(session: Optional[str] = None) -> None:
    ensure_api_key()
    try:
        threads = asyncio.run(list_threads(DB_PATH))
    except Exception:
        threads = []

    thread_id = session or select_session_tui()

    engine = ChatEngine()
    try:
        history = asyncio.run(engine.get_visible_history(thread_id))
    except Exception:
        history = []

    if thread_id not in threads:
        threads.insert(0, thread_id)

    TiagaTUI(thread_id, history=history, all_threads=threads).run()


def main() -> None:
    run_tui()


if __name__ == "__main__":
    main()
