"""
ui/app.py
---------
The Textual application with two screens:

  ChatScreen      – the main streaming chat view (reference image 1)
  ApprovalScreen  – the diff / approval view (reference image 2)

Public API that the rest of tiaga calls:
  TiagaApp.run_sync()              – blocks until app exits
  app.post_assistant_delta(text)   – stream a token
  app.post_tool_start(...)         – show a running tool card
  app.post_tool_end(...)           – finalise the tool card
  app.post_plan(items)             – show/update the plan panel
  app.request_approval(...)        – push ApprovalScreen, await result
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any
import signal
import time

from rich.syntax import Syntax
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult, ScreenStackError
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical, Horizontal
from textual.geometry import Size
from textual.screen import Screen
from textual.widgets import Input, Static

from .theme import TEXTUAL_CSS
from .widgets import (
    ApprovalSidebar,
    AssistantMessage,
    DiffView,
    FooterBar,
    InputBar,
    PlanPanel,
    RainbowBorder,
    ToolCallBlock,
    UserMessage,
)

try:
    from textual.drivers.linux_driver import LinuxDriver
except Exception:
    LinuxDriver = None  # type: ignore[assignment]


class ThreadSafeLinuxDriver(LinuxDriver if LinuxDriver is not None else object):  # type: ignore[misc]
    """Linux driver variant that skips signal registration for worker-thread use."""

    @staticmethod
    def _run_without_signal_registration(fn: Any) -> Any:
        if threading.current_thread() is threading.main_thread():
            return fn()

        original_signal = signal.signal

        def _safe_signal(_sig: Any, _handler: Any) -> Any:
            # Signal handlers are process-global and only legal from main thread.
            return signal.SIG_DFL

        signal.signal = _safe_signal  # type: ignore[assignment]
        try:
            return fn()
        finally:
            signal.signal = original_signal  # type: ignore[assignment]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if LinuxDriver is None:
            raise RuntimeError("Linux Textual driver is unavailable")
        self._run_without_signal_registration(lambda: LinuxDriver.__init__(self, *args, **kwargs))
        self._resize_poll_stop = threading.Event()
        self._resize_poll_thread: threading.Thread | None = None
        self._last_polled_size: tuple[int, int] | None = None

    def _start_resize_poller(self) -> None:
        if self._resize_poll_thread and self._resize_poll_thread.is_alive():
            return
        self._resize_poll_stop.clear()

        def _poll() -> None:
            while not self._resize_poll_stop.is_set():
                try:
                    size = self._get_terminal_size()
                    if size != self._last_polled_size:
                        self._last_polled_size = size
                        width, height = size
                        event = events.Resize(Size(width, height), Size(width, height))
                        loop = getattr(self._app, "_loop", None)
                        if loop and not loop.is_closed():
                            asyncio.run_coroutine_threadsafe(
                                self._app._post_message(event),  # type: ignore[attr-defined]
                                loop=loop,
                            )
                except Exception:
                    pass
                time.sleep(0.2)

        self._resize_poll_thread = threading.Thread(
            target=_poll,
            daemon=True,
            name="textual-resize-poll",
        )
        self._resize_poll_thread.start()

    def start_application_mode(self) -> None:
        self._run_without_signal_registration(lambda: LinuxDriver.start_application_mode(self))
        # In worker-thread mode, SIGWINCH callbacks are unavailable.
        # Poll terminal size and synthesize resize events.
        if threading.current_thread() is not threading.main_thread():
            self._start_resize_poller()

    def disable_input(self) -> None:
        self._resize_poll_stop.set()
        if self._resize_poll_thread and self._resize_poll_thread.is_alive():
            self._resize_poll_thread.join(timeout=0.5)
        self._run_without_signal_registration(lambda: LinuxDriver.disable_input(self))


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────

def _guess_lang(path: str | None) -> str:
    if not path:
        return "text"
    return {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".jsx": "jsx", ".tsx": "tsx", ".json": "json", ".toml": "toml",
        ".yaml": "yaml", ".yml": "yaml", ".md": "markdown",
        ".sh": "bash", ".bash": "bash", ".rs": "rust", ".go": "go",
        ".css": "css", ".html": "html", ".xml": "xml", ".sql": "sql",
        ".c": "c", ".cpp": "cpp", ".java": "java",
    }.get(Path(path).suffix.lower(), "text")


# ─────────────────────────────────────────────────────────────────────────────
# ChatScreen
# ─────────────────────────────────────────────────────────────────────────────

class ChatScreen(Screen):
    """Main streaming chat screen — reference image 1."""

    CSS = TEXTUAL_CSS

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("f1", "show_help", "Help"),
        Binding("f2", "show_settings", "Settings"),
        Binding("ctrl+b", "toggle_sidebar", "Sidebar"),
        Binding("escape", "dismiss_focus", "Dismiss"),
    ]

    def __init__(self, title: str, cwd: str, mode: str = "Default", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._cwd = cwd
        self._mode = mode
        self._current_assistant: AssistantMessage | None = None
        self._assistant_placeholder_active = False
        self._tool_blocks: dict[str, ToolCallBlock] = {}
        # Futures used for user input (slash commands / free text)
        self._pending_input: asyncio.Future[str] | None = None

    def on_mount(self) -> None:
        try:
            self.query_one("#chat-input", Input).focus()
        except Exception:
            pass
        self._apply_responsive_layout(self.size.width)

    def on_resize(self, _event: Any) -> None:
        self._apply_responsive_layout(self.size.width)
    async def add_user_message(self, text: str) -> None:
        msg = UserMessage()
        msg.set_text(text)
        await self._mount_widget(msg)
    def _apply_responsive_layout(self, width: int) -> None:
        try:
            header_path = self.query_one("#header-path", Static)
            header_mode = self.query_one("#header-mode", Static)
            scroll = self.query_one("#messages-scroll", ScrollableContainer)
        except Exception:
            return

        if width < 80:
            header_path.styles.display = "none"
            header_mode.styles.display = "none"
            scroll.styles.padding = (0, 0)
        elif width < 110:
            header_path.styles.display = "none"
            header_mode.styles.display = "block"
            scroll.styles.padding = (0, 1)
        else:
            header_path.styles.display = "block"
            header_mode.styles.display = "block"
            scroll.styles.padding = (0, 2)

    # ── compose ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield RainbowBorder(id="rainbow-border")
        with Static(id="header"):
            yield Static(f"🐸  {self._title}", id="header-title", markup=False)
            yield Static(f" {self._cwd}", id="header-path", markup=False)
            yield Static(self._mode, id="header-mode", markup=False)
        with ScrollableContainer(id="messages-scroll"):
            pass   # messages are mounted here dynamically
        yield InputBar(id="input-bar")
        yield FooterBar(id="footer")

    # ── internal mount helpers ─────────────────────────────────────────────────
    def on_paste(self, event: events.Paste) -> None:
        try:
            input_box = self.query_one("#chat-input", Input)
            input_box.insert_text(event.text)
        except Exception:
            pass
    def _scroll(self) -> ScrollableContainer:
        return self.query_one("#messages-scroll", ScrollableContainer)

    async def _mount_widget(self, widget: Static) -> None:
        """Mount a new widget in the scroll area and scroll to bottom."""
        await self._scroll().mount(widget)
        self._scroll().scroll_end(animate=False)

    # ── public API (called from TUI bridge) ───────────────────────────────────

    async def start_assistant_block(self, placeholder: str | None = None) -> None:
        """Begin a new streaming assistant message block."""
        self._current_assistant = AssistantMessage()
        if placeholder:
            self._current_assistant.set_text(placeholder)
            self._assistant_placeholder_active = True
        else:
            self._assistant_placeholder_active = False
        await self._mount_widget(self._current_assistant)

    def stream_delta(self, delta: str) -> None:
        """Append a streaming token to the current assistant block."""
        if self._current_assistant is None:
            return
        if self._assistant_placeholder_active:
            self._current_assistant.set_text(delta)
            self._assistant_placeholder_active = False
        else:
            self._current_assistant.append(delta)
        self._scroll().scroll_end(animate=False)

    def end_assistant_block(self) -> None:
        if self._current_assistant is not None and self._assistant_placeholder_active:
            # If no real content arrived, remove the placeholder block.
            self._current_assistant.remove()
        self._assistant_placeholder_active = False
        self._current_assistant = None

    def set_current_assistant_text(self, text: str) -> None:
        """Replace the current streaming assistant block text in-place."""
        if self._current_assistant is None:
            return
        self._current_assistant.set_text(text)
        # Keep placeholder mode so end_assistant_block can remove this
        # loading-only block if no real assistant content arrives.
        self._assistant_placeholder_active = True
        self._scroll().scroll_end(animate=False)

    async def add_tool_start(
        self,
        call_id: str,
        tool_kind: str,
        name: str,
        arguments: dict[str, Any],
    ) -> None:
        existing = self._tool_blocks.get(call_id)
        if existing:
            existing.tool_kind = tool_kind
            existing.tool_name = name
            existing.update_arguments(arguments)
            self._scroll().scroll_end(animate=False)
            return

        block = ToolCallBlock(
            call_id=call_id,
            tool_kind=tool_kind,
            name=name,
            arguments=arguments,
            id=f"tool-{call_id}",
        )
        self._tool_blocks[call_id] = block
        await self._mount_widget(block)

    def finish_tool(
        self,
        call_id: str,
        success: bool,
        renderables: list[Any],
        error: str | None = None,
    ) -> None:
        block = self._tool_blocks.get(call_id)
        if block:
            block.mark_done(success=success, output_renderables=renderables, error=error)
            self._scroll().scroll_end(animate=False)

    async def add_plan(self, items: list[tuple[str, str]]) -> None:
        """Show (or replace the last) plan panel."""
        panel = PlanPanel(items=items)
        await self._mount_widget(panel)

    async def add_assistant_text(self, text: str) -> None:
        """Mount a non-streaming assistant message."""
        msg = AssistantMessage()
        msg.set_text(text)
        await self._mount_widget(msg)

    # ── input handling ─────────────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "chat-input":
            return
        text = event.value.strip()
        event.input.value = ""
        if self._pending_input and not self._pending_input.done():
            self._pending_input.set_result(text)

    def wait_for_input(self) -> asyncio.Future[str]:
        """Return a Future that resolves when the user presses Enter."""
        loop = asyncio.get_event_loop()
        self._pending_input = loop.create_future()
        return self._pending_input

    # ── actions ───────────────────────────────────────────────────────────────

    def action_quit(self) -> None:
        self.app.exit()

    def action_show_help(self) -> None:
        self.app.push_screen("help")

    def action_show_settings(self) -> None:
        pass  # TODO

    def action_toggle_sidebar(self) -> None:
        pass  # TODO

    def action_dismiss_focus(self) -> None:
        self.query_one("#chat-input", Input).blur()


# ─────────────────────────────────────────────────────────────────────────────
# ApprovalScreen
# ─────────────────────────────────────────────────────────────────────────────

class ApprovalScreen(Screen):
    """
    Diff / approval screen — reference image 2.
    Returns one of: "always_allow" | "allow" | "reject"
    """

    CSS = TEXTUAL_CSS

    BINDINGS = [
    Binding("ctrl+c", "quit", "Quit", show=False),
    Binding("ctrl+shift+v", "paste_clipboard", "Paste",show=True),
    Binding("f1", "show_help", "Help"),
    Binding("f2", "show_settings", "Settings"),
    Binding("ctrl+b", "toggle_sidebar", "Sidebar"),
    Binding("escape", "dismiss_focus", "Dismiss"),
]

    def __init__(
        self,
        filename: str,
        content: str,
        added: int = 0,
        removed: int = 0,
        description: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._filename    = filename
        self._content     = content
        self._added       = added
        self._removed     = removed
        self._description = description
        self._sidebar: ApprovalSidebar | None = None
        self._result_future: asyncio.Future[str] | None = None

    def compose(self) -> ComposeResult:
        yield RainbowBorder(id="rainbow-border")
        with Static(id="header"):
            yield Static("🐸  Toad — Approval Request", id="header-title", markup=False)
        with Horizontal(id="approval-screen"):
            yield ApprovalSidebar(
                filenames=[Path(self._filename).name],
                id="approval-sidebar",
            )
            yield DiffView(
                filename=self._filename,
                content=self._content,
                added=self._added,
                removed=self._removed,
                language=_guess_lang(self._filename),
                id="diff-view",
            )
        yield self._make_footer()

    def _make_footer(self) -> Static:
        s = Static(id="footer")
        s.update(
            "  [bold #89b4fa]↑↓[/] Cursor  "
            "[bold #89b4fa]aA[/] Allow once/always  "
            "[bold #89b4fa]r[/] Reject once  "
            "[bold #89b4fa]tab[/] Focus  "
            "[bold #89b4fa]jk[/] Navigation  "
            "[bold #89b4fa]f1[/] Help  "
            "[bold #89b4fa]^p[/] palette",
            markup=True,
        )
        s.styles.background = "#181825"
        s.styles.height = 1
        s.styles.padding = (0, 1)
        return s

    def on_mount(self) -> None:
        self._sidebar = self.query_one("#approval-sidebar", ApprovalSidebar)

    # ── actions ───────────────────────────────────────────────────────────────

    def action_move_up(self) -> None:
        if self._sidebar:
            self._sidebar.select_prev()

    def action_move_down(self) -> None:
        if self._sidebar:
            self._sidebar.select_next()

    def action_confirm(self) -> None:
        action = self._sidebar.selected_action if self._sidebar else "reject"
        self._resolve(action)

    def action_reject(self) -> None:
        self._resolve("reject")

    def action_allow(self) -> None:
        self._resolve("allow")

    def action_always_allow(self) -> None:
        self._resolve("always_allow")

    def _resolve(self, action: str) -> None:
        if self._result_future and not self._result_future.done():
            self._result_future.set_result(action)
        self.dismiss(action)

    def set_future(self, fut: asyncio.Future[str]) -> None:
        self._result_future = fut


# ─────────────────────────────────────────────────────────────────────────────
# TiagaApp
# ─────────────────────────────────────────────────────────────────────────────

class TiagaApp(App):
    """
    Root application.  Owns ChatScreen and can push ApprovalScreen on demand.
    """

    TITLE = "Toad"
    CSS = TEXTUAL_CSS

    def __init__(
        self,
        title: str,
        cwd: str,
        mode: str = "Default",
        mounted_event: threading.Event | None = None,
        **kwargs: Any,
    ) -> None:
        driver_class = kwargs.pop("driver_class", None)
        if driver_class is None and LinuxDriver is not None:
            driver_class = ThreadSafeLinuxDriver
        super().__init__(driver_class=driver_class, **kwargs)
        self._chat_screen = ChatScreen(title=title, cwd=cwd, mode=mode)
        self._mounted_event = mounted_event

    def on_mount(self) -> None:
        self.push_screen(self._chat_screen)
        if self._mounted_event is not None:
            self._mounted_event.set()

    # ── bridge methods (called from sync TUI wrapper via call_from_thread) ────

    @property
    def chat(self) -> ChatScreen:
        return self._chat_screen

    async def request_approval(
        self,
        filename: str,
        content: str,
        added: int = 0,
        removed: int = 0,
        description: str = "",
    ) -> str:
        """
        Push the ApprovalScreen, block until the user picks an action,
        then return "always_allow" | "allow" | "reject".
        """
        loop  = asyncio.get_event_loop()
        fut: asyncio.Future[str] = loop.create_future()
        screen = ApprovalScreen(
            filename=filename,
            content=content,
            added=added,
            removed=removed,
            description=description,
        )
        screen.set_future(fut)
        self.push_screen(screen)
        result = await fut
        return result
    
    def exit(self):
        super().exit()
