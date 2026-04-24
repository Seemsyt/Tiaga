from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme
from rich.align import Align
from rich.padding import Padding

from tiaga.config.config import Config
from tiaga.tools_manager.base import ToolConfirmation


# ── Theme ─────────────────────────────────────────────────────────

TIAGA_THEME = Theme({
    "primary": "bold color(87)",
    "secondary": "color(105)",
    "muted": "color(244)",
    "dim": "dim color(244)",
    "success": "bold color(78)",
    "error": "bold color(203)",
    "warning": "bold color(220)",
})


# ── UI ────────────────────────────────────────────────────────────

class ModernUI:
    def __init__(self, config: Config):
        self.config = config
        self.console = Console(theme=TIAGA_THEME)
        self.streaming = False

    # ── HEADER / WELCOME ──────────────────────────────────────────

    def print_welcome(self):
        header = Text()
        header.append("TIAGA", style="primary")
        header.append("  •  ", style="dim")
        header.append(self.config.model_name or "no-model", style="secondary")

        panel = Panel(
            Align.center(header),
            border_style="dim",
            padding=(0, 2),
        )

        self.console.print(panel)

    # ── USER INPUT ────────────────────────────────────────────────

    def prompt_user(self) -> str:
        return input("\n❯ ")

    # ── ASSISTANT MESSAGE (Claude-style bubble) ───────────────────

    def assistant(self, text: str):
        bubble = Panel(
            Padding(text, (0, 1)),
            border_style="secondary",
        )
        self.console.print(bubble)

    # ── STREAMING OUTPUT ──────────────────────────────────────────

    def stream(self, content: str):
        if not self.streaming:
            self.console.print("\n", end="")
            self.streaming = True

        self.console.print(content, end="")

    def end_stream(self):
        if self.streaming:
            self.console.print()
            self.streaming = False

    # ── TOOL CALL ─────────────────────────────────────────────────

    def _extract_path_hint(self, arguments: dict[str, Any]) -> str | None:
        for key in ("path", "file_path", "filepath", "directory", "dir", "workdir", "cwd"):
            if key not in arguments:
                continue
            value = arguments.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
                first = value[0]
                remaining = len(value) - 1
                return f"{first} (+{remaining} more)" if remaining > 0 else first
        return None

    def _preview_tool_args(self, value: Any, *, depth: int = 0) -> Any:
        if depth >= 3:
            return "…"
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            max_len = 180
            if len(value) <= max_len:
                return value
            return value[:max_len] + "…"
        if isinstance(value, dict):
            preview: dict[str, Any] = {}
            for k, v in value.items():
                if isinstance(k, str) and k in {"content", "patch", "text", "data", "diff"} and isinstance(v, str):
                    preview[k] = self._preview_tool_args(v, depth=depth + 1)
                else:
                    preview[str(k)] = self._preview_tool_args(v, depth=depth + 1)
            return preview
        if isinstance(value, list):
            if len(value) <= 20:
                return [self._preview_tool_args(v, depth=depth + 1) for v in value]
            head = [self._preview_tool_args(v, depth=depth + 1) for v in value[:20]]
            head.append(f"…(+{len(value) - 20} more)")
            return head
        return str(value)

    def render_tool_call_start(self, name: str, arguments: dict):
        path_hint = self._extract_path_hint(arguments)
        preview_args = self._preview_tool_args(arguments)

        title = Text()
        title.append("⟳ ", style="dim")
        title.append(f"Running {name}", style="primary")

        body = Text()
        if path_hint:
            body.append("path: ", style="muted")
            body.append(path_hint, style="secondary")
            body.append("\n")

        try:
            args_text = json.dumps(preview_args, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        except Exception:
            args_text = repr(preview_args)

        if args_text and args_text != "{}":
            body.append("args:\n", style="muted")
            body.append(args_text, style="dim")

        panel = Panel(body, title=title, border_style="dim")
        self.console.print(panel)

    def render_tool_call_end(self, name: str, success: bool, error: str | None = None):
        style = "success" if success else "error"
        icon = "✓" if success else "✗"
        label = f"{icon} {name}" + (f": {error}" if error else "")

        panel = Panel(label, border_style=style)
        self.console.print(panel)

    # ── APPROVAL ──────────────────────────────────────────────────

    def handle_confirmation(self, confirmation: ToolConfirmation) -> bool:
        text = Text()
        text.append("⚠ Approval Required\n", style="warning")
        text.append(confirmation.tool_name, style="primary")

        panel = Panel(text, border_style="warning")
        self.console.print(panel)

        resp = input("Allow? [y/N]: ").lower()
        return resp in ("y", "yes")

    # ── SYSTEM / NOTE MESSAGE ─────────────────────────────────────

    def post_message(self, msg: str):
        self.console.print(
            Panel(msg, border_style="dim")
        )

    # ── EXIT ──────────────────────────────────────────────────────

    def shutdown(self):
        self.console.print(
            Panel("Goodbye.", border_style="dim")
        )
