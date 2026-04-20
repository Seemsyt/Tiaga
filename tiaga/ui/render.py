"""
ui/render.py
------------
Textual-powered TUI bridge used by the CLI.

Public surface kept stable for existing call sites.
"""

from __future__ import annotations

import asyncio
import re
import threading
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.syntax import Syntax
from rich.text import Text

from tiaga.config.config import Config
from tiaga.context.text import truncate_text
from tiaga.tools_manager.base import ToolConfirmation
from tiaga.utils.path import display_path_relative_to_cwd

from .app import TiagaApp
from .theme import RICH_THEME


_console: Console | None = None


def _get_console() -> Console:
    global _console
    if _console is None:
        _console = Console(theme=RICH_THEME, highlight=False)
    return _console


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────

def _guess_language(path: str | None) -> str:
    if not path:
        return "text"
    return {
        ".py": "python", ".js": "javascript", ".jsx": "jsx",
        ".ts": "typescript", ".tsx": "tsx", ".json": "json",
        ".toml": "toml", ".yaml": "yaml", ".yml": "yaml",
        ".md": "markdown", ".sh": "bash", ".bash": "bash",
        ".zsh": "bash", ".rs": "rust", ".go": "go",
        ".java": "java", ".kt": "kotlin", ".swift": "swift",
        ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp",
        ".css": "css", ".html": "html", ".xml": "xml", ".sql": "sql",
    }.get(Path(path).suffix.lower(), "text")


def _extract_read_file_code(text: str) -> tuple[int, str] | None:
    """Parse the 'N|code' format returned by read_file."""
    body = text
    header_match = re.match(r"^Showing lines (\d+)-(\d+) of (\d+)\n\n", text)
    if header_match:
        body = text[header_match.end():]

    code_lines: list[str] = []
    start_line: int | None = None
    for line in body.splitlines():
        m = re.match(r"^\s*(\d+)\|(.*)$", line)
        if not m:
            continue
        line_no = int(m.group(1))
        if start_line is None:
            start_line = line_no
        code_lines.append(m.group(2))

    if start_line is None:
        return None
    return start_line, "\n".join(code_lines)


# ─────────────────────────────────────────────────────────────────────────────
# TUI
# ─────────────────────────────────────────────────────────────────────────────

class TUI:
    """
    Textual-powered terminal UI.

    The TiagaApp runs in a dedicated thread. Public methods remain synchronous
    for the caller and marshal work onto the app loop.
    """

    def __init__(self, console: Console | None, config: Config) -> None:
        self.config = config
        self.cwd = config.cwd

        self._rich_console = console or _get_console()

        self._app: TiagaApp | None = None
        self._app_thread: threading.Thread | None = None
        self._app_loop: asyncio.AbstractEventLoop | None = None
        self._app_loop_ready = threading.Event()
        self._app_mounted = threading.Event()

        self._tool_args: dict[str, dict[str, Any]] = {}
        self._streaming = False
        self._first_token_seen = False

    # ── app lifecycle ────────────────────────────────────────────────────────

    def _ensure_app(self) -> TiagaApp:
        if self._app is not None:
            return self._app

        project_name = Path(self.cwd).name if self.cwd else "tiaga"
        app = TiagaApp(
            title=f"Toad — {project_name}",
            cwd=str(self.cwd or "."),
            mounted_event=self._app_mounted,
        )
        self._app = app

        def _run() -> None:
            async def _inner() -> None:
                self._app_loop = asyncio.get_event_loop()
                self._app_loop_ready.set()
                await app.run_async()

            asyncio.run(_inner())

        self._app_thread = threading.Thread(target=_run, daemon=True, name="textual-app")
        self._app_thread.start()
        self._app_loop_ready.wait(timeout=10)
        self._app_mounted.wait(timeout=10)
        return app

    def _call(self, coro: Any, timeout: float | None = 30) -> Any:
        self._ensure_app()
        loop = self._app_loop
        if loop is None:
            return None
        if loop is None or loop.is_closed():
            return None

        try:
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=timeout)
        except Exception:
            return None

    def _post(self, fn: Any, *args: Any) -> None:
        app = self._ensure_app()
        if self._app_loop and not self._app_loop.is_closed():
            try:
                app.call_from_thread(fn, *args)
            except Exception:
                pass

    # ── welcome / help ───────────────────────────────────────────────────────

    def print_welcome(self, title: str, lines: list[str]) -> None:
        # Ensure Textual app is visible as the primary interface.
        self._ensure_app()

        # Render a short startup message as assistant text in a blocking manner
        # to guarantee ordering with subsequent _ui_note calls.
        startup = f"{title}\n" + "\n".join(lines)
        async def _welcome():
            chat = self._ensure_app().chat
            await chat.start_assistant_block()
            chat.stream_delta(startup)
            chat.end_assistant_block()
        self._call(_welcome())

    def show_help(self) -> None:
        help_text = (
            """
## Commands

- `/help` - Show this help
- `/exit` or `/quit` - Exit the agent
- `/clear` - Clear conversation history
- `/config` - Show current configuration
- `/model <name>` - Change the model
- `/approval <mode>` - Change approval mode
- `/stats` - Show session statistics
- `/tools` - List available tools
- `/mcp` - Show MCP server status
- `/save` - Save current session
- `/checkpoint [name]` - Create a checkpoint
- `/checkpoints` - List available checkpoints
- `/restore <checkpoint_id>` - Restore a checkpoint
- `/sessions` - List saved sessions
- `/resume <session_id>` - Resume a saved session

## Tips

- Just type your message to chat with the agent
- The agent can read, write, and execute code
- Some operations require approval (can be configured)
"""
        )
        self._call(self._ensure_app().chat.start_assistant_block())
        self._post(self._ensure_app().chat.stream_delta, help_text)
        self._post(self._ensure_app().chat.end_assistant_block)

    # ── streaming ────────────────────────────────────────────────────────────

    def begin_streaming(self, loading_text: str | None = "Thinking...") -> None:
        """
        Start a temporary thinking block.
        This block is NOT the final answer.
        """
        self._streaming = True
        self._first_token_seen = False

        async def _start():
            await self._ensure_app().chat.start_assistant_block(loading_text)

        self._call(_start())


    def stream_assistant_delta(self, content: str) -> None:
        """
        Stream tokens into the current assistant block.
        """
        if not self._streaming:
            return

        self._first_token_seen = True

        async def _stream():
            self._ensure_app().chat.stream_delta(content)

        self._call(_stream())


    def end_assistance(self) -> None:
        """
        Ends ONLY the thinking block.
        """
        self._streaming = False
        self._first_token_seen = False

        async def _end():
            self._ensure_app().chat.end_assistant_block()

        self._call(_end())


    # ✅ NEW: FINAL ANSWER (separate clean block)

    def start_final_answer(self) -> None:
        """
        Start a clean assistant block for final answer.
        """
        async def _start():
            await self._ensure_app().chat.start_assistant_block()

        self._call(_start())


    def stream_final_answer(self, content: str) -> None:
        """
        Stream final answer tokens.
        """
        async def _stream():
            self._ensure_app().chat.stream_delta(content)

        self._call(_stream())


    def end_final_answer(self) -> None:
        """
        End final answer block.
        """
        async def _end():
            self._ensure_app().chat.end_assistant_block()

        self._call(_end())

    # ── plan panel ───────────────────────────────────────────────────────────

    def post_plan(self, items: list[tuple[str, str]]) -> None:
        self._call(self._ensure_app().chat.add_plan(items))

    # ── tool calls ───────────────────────────────────────────────────────────

    def render_tool_call_start(
        self,
        call_id: str,
        tool_kind: str,
        name: str,
        arguments: dict[str, Any] | Any,
    ) -> None:
        normalized_args: dict[str, Any]
        if isinstance(arguments, dict):
            normalized_args = arguments
        else:
            normalized_args = {"raw_arguments": arguments}
        self._tool_args[call_id] = normalized_args

        display_args = dict(normalized_args)
        for key in ("path", "cwd"):
            val = display_args.get(key)
            if isinstance(val, str) and self.cwd:
                display_args[key] = str(display_path_relative_to_cwd(val, self.cwd))

        async def _add_tool():
            await self._ensure_app().chat.add_tool_start(
                call_id=call_id,
                tool_kind=tool_kind,
                name=name,
                arguments=display_args,
            )
        self._call(_add_tool())

    def render_tool_call_end(
        self,
        call_id: str,
        tool_kind: str,
        name: str,
        success: bool,
        error: str | None = None,
        output: str | None = None,
        metadata: dict[str, Any] | None = None,
        diff: str | None = None,
        truncated: bool = False,
        exit_code: int | None = None,
    ) -> None:
        args = self._tool_args.get(call_id, {})
        renderables = self._build_tool_output_renderables(
            name=name,
            success=success,
            error=error,
            output=output,
            metadata=metadata or {},
            diff=diff,
            truncated=truncated,
            exit_code=exit_code,
            args=args,
        )
        async def _finish():
            self._ensure_app().chat.finish_tool(
                call_id,
                success,
                renderables,
                error,
            )
        self._call(_finish())

    # ── confirmation / approval ──────────────────────────────────────────────

    def handle_confirmation(self, confirmation: ToolConfirmation) -> bool:
        """
        Show ApprovalScreen and block until the user picks Allow / Reject.
        Returns True if allowed (once or always).
        """
        diff_text = ""
        added = removed = 0
        if confirmation.diff:
            diff_text = confirmation.diff.create_diff()
            for line in diff_text.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    added += 1
                elif line.startswith("-") and not line.startswith("---"):
                    removed += 1

        filename = getattr(confirmation, "path", "") or confirmation.tool_name

        result: str = self._call(
            self._ensure_app().request_approval(
                filename=str(filename),
                content=diff_text or confirmation.description,
                added=added,
                removed=removed,
                description=confirmation.description,
            )
        )
        return result in {"allow", "always_allow"}

    # ── user input ───────────────────────────────────────────────────────────

    def prompt_user(self, prompt_text: str = "") -> str:
        _ = prompt_text
        value = self._call(self._wrap_wait_for_input(), timeout=None)
        return value if isinstance(value, str) else ""

    async def _wrap_wait_for_input(self) -> str:
        return await self._ensure_app().chat.wait_for_input()

    def post_message(self, text: str) -> None:
        if not text:
            return
        if self._app_loop and not self._app_loop.is_closed():
            self._call(self._ensure_app().chat.add_assistant_text(text))
    # ── output-renderables builder ───────────────────────────────────────────

    def _build_tool_output_renderables(
        self,
        name: str,
        success: bool,
        error: str | None,
        output: str | None,
        metadata: dict[str, Any],
        diff: str | None,
        truncated: bool,
        exit_code: int | None,
        args: dict[str, Any],
    ) -> list[Any]:
        blocks: list[Any] = []
        primary_path: str | None = None
        if isinstance(metadata.get("path"), str):
            primary_path = metadata["path"]

        if name == "read_file" and success and primary_path:
            parsed = _extract_read_file_code(output or "")
            if parsed:
                start_line, code = parsed
                lang = _guess_language(primary_path)
                rel = display_path_relative_to_cwd(primary_path, self.cwd)
                s_st = metadata.get("shown_start", "")
                s_en = metadata.get("shown_end", "")
                total = metadata.get("total_lines", "")
                hdr_parts = [str(rel), " ⦁ "]
                if s_st and s_en and total:
                    hdr_parts.append(f"lines {s_st}-{s_en} of {total}")
                blocks.append(Text("".join(hdr_parts), style="#6c7086"))
                blocks.append(
                    Syntax(
                        code,
                        lang,
                        theme="monokai",
                        line_numbers=True,
                        start_line=start_line,
                        word_wrap=True,
                    )
                )

        elif name in {"write_file", "edit"} and success and diff:
            out_line = (output or "").strip() or "completed"
            blocks.append(Text(out_line, style="#6c7086"))
            disp = truncate_text(diff, self.config.model_name, 240)
            blocks.append(Syntax(disp, "diff", theme="monokai", word_wrap=True))

        elif name == "shell" and success:
            cmd = args.get("command", "")
            if isinstance(cmd, str) and cmd.strip():
                blocks.append(Text(f"$ {cmd.strip()}", style="#a6e3a1 bold"))
            if exit_code is not None:
                blocks.append(Text(f"exit_code={exit_code}", style="#6c7086"))
            shell_text = output or ""
            disp = truncate_text(shell_text, self.config.model_name, 240)
            if disp.strip():
                blocks.append(Syntax(disp, "text", theme="monokai", word_wrap=True))

        elif name == "grep" and success:
            parts = []
            if isinstance(metadata.get("matches"), int):
                parts.append(f"{metadata['matches']} matches")
            if isinstance(metadata.get("files_searched"), int):
                parts.append(f"{metadata['files_searched']} files searched")
            if parts:
                blocks.append(Text(" ⦁ ".join(parts), style="#6c7086"))
            if output:
                blocks.append(Syntax(output, "text", theme="monokai", word_wrap=True))

        elif name == "glob" and success:
            matches = metadata.get("matches")
            if isinstance(matches, list):
                blocks.append(Text(f"{len(matches)} matches", style="#6c7086"))
            if output:
                blocks.append(Syntax(output, "text", theme="monokai", word_wrap=True))
            else:
                blocks.append(Text("No files matched.", style="#6c7086"))

        elif name == "web_search" and success:
            parts = []
            if isinstance(metadata.get("lines"), int):
                parts.append(f"{metadata['lines']} lines")
            if isinstance(metadata.get("query"), str):
                parts.append(f"query: {metadata['query']}")
            if parts:
                blocks.append(Text(" ⦁ ".join(parts), style="#6c7086"))
            if output:
                blocks.append(Syntax(output, "text", theme="monokai", word_wrap=True))

        elif name == "web_fetch" and success:
            parts = []
            if isinstance(metadata.get("status_code"), int):
                parts.append(str(metadata["status_code"]))
            if isinstance(metadata.get("content_length"), int):
                parts.append(f"{metadata['content_length']} bytes")
            url = args.get("url")
            if isinstance(url, str):
                parts.append(url)
            if parts:
                blocks.append(Text(" • ".join(parts), style="#6c7086"))
            disp = truncate_text(output or "", self.config.model_name, 240)
            blocks.append(Syntax(disp, "text", theme="monokai", word_wrap=True))

        elif name == "list_dir" and success:
            listed = primary_path or args.get("path", ".")
            recursive = metadata.get("recursive", False)
            total = metadata.get("total_entries", "")
            is_truncated = metadata.get("truncated", False)
            hdr = str(display_path_relative_to_cwd(listed, self.cwd))
            if recursive:
                hdr += "  🌲 recursive"
            if total:
                hdr += f"  ⦁  {total} entries"
            blocks.append(Text(hdr, style="#6c7086"))
            lines = (output or "").splitlines()
            dir_text = "\n".join(l for l in lines if not l.strip().startswith("Total entries:")).strip()
            disp = truncate_text(dir_text, self.config.model_name, 240)
            if disp.strip():
                blocks.append(Syntax(disp, "text", theme="monokai", word_wrap=False))
            if is_truncated:
                blocks.append(Text("⚠ listing truncated", style="yellow"))

        elif name == "todos" and success:
            disp = truncate_text(output or "", self.config.model_name, 400)
            blocks.append(Syntax(disp, "text", theme="monokai", word_wrap=True))

        elif name == "memory" and success:
            parts = []
            if isinstance(args.get("action"), str):
                parts.append(args["action"])
            if isinstance(args.get("key"), str):
                parts.append(args["key"])
            if isinstance(metadata.get("found"), bool):
                parts.append("found" if metadata["found"] else "missing")
            if parts:
                blocks.append(Text(" • ".join(parts), style="#6c7086"))
            disp = truncate_text(output or "", self.config.model_name, 400)
            blocks.append(Syntax(disp, "text", theme="monokai", word_wrap=True))

        elif name == "youtube_transcript" and success:
            parts = []
            if metadata.get("video_id"):
                parts.append(f"Video ID: {metadata['video_id']}")
            if metadata.get("length"):
                parts.append(f"Length: {metadata['length']} chars")
            if parts:
                blocks.append(Text(" ⦁ ".join(parts), style="#6c7086"))
            if output:
                blocks.append(Syntax(output, "text", theme="monokai", word_wrap=True))
            else:
                blocks.append(Text("No transcript found.", style="#6c7086"))

        elif success and output:
            blocks.append(Text(output, style="#cdd6f4"))

        if error and not success:
            blocks.append(Text(error, style="#f38ba8 bold"))
            disp = truncate_text(output or "", "gpt-4o-mini", 240)
            if disp.strip():
                blocks.append(Text(disp, style="#6c7086"))

        if truncated:
            blocks.append(Text("⚠ tool output was truncated", style="yellow"))

        return blocks
    
    def add_user_message(self, text: str):
        coro = self._ensure_app().chat.add_user_message(text)
        self._call(coro)
    
    def shutdown(self):
        if self._app:
            try:
                self._app.call_from_thread(self._app.exit)
            except Exception:
                pass
    def set_current_assistant_text(self, text: str) -> None:
        self._post(self._ensure_app().chat.set_current_assistant_text, text)

        if self._app_thread and self._app_thread.is_alive():
            self._app_thread.join(timeout=2)
