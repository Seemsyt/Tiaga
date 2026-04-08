
from pathlib import Path
from typing import Any,Tuple

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.console import Console,Group
from rich.rule import Rule
from rich.theme import Theme
from rich import box
import json
from tiaga.config.config import Config
from tiaga.context.text import truncate_text
from tiaga.utils.path import resolve_path,display_path_relative_to_cwd
import re
from rich.syntax import Syntax

AGENT_THEME = Theme(
    {
        # General
        "info": "cyan",
        "warning": "yellow",
        "error": "bright_red bold",
        "success": "green",
        "dim": "dim",
        "muted": "grey50",
        "border": "grey35",
        "highlight": "bold cyan",
        # Roles
        "user": "bright_blue bold",
        "assistant": "bright_white",
        # Tools
        "tool": "bright_magenta bold",
        "tool.read": "cyan",
        "tool.write": "yellow",
        "tool.shell": "magenta",
        "tool.network": "bright_blue",
        "tool.memory": "green",
        "tool.mcp": "bright_cyan",
        # Code / blocks
        "code": "white",
    }
)

_console :Console|None = None
def _guess_language(path: str | None) -> str:
        if not path:
            return "text"
        suffix = Path(path).suffix.lower()
        return {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "jsx",
            ".ts": "typescript",
            ".tsx": "tsx",
            ".json": "json",
            ".toml": "toml",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
            ".sh": "bash",
            ".bash": "bash",
            ".zsh": "bash",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".kt": "kotlin",
            ".swift": "swift",
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".hpp": "cpp",
            ".css": "css",
            ".html": "html",
            ".xml": "xml",
            ".sql": "sql",
        }.get(suffix, "text")

def _get_console():
    global _console
    if _console is None:
        _console = Console(theme=AGENT_THEME,highlight=False)
    return _console
    
class TUI:
    def __init__(self,console:Console|None,config:Config)->None:
       self.console = console or _get_console()
       self.assistance_stream_open = False
       self.tool_args_by_call_id:dict[str,dict[str,Any]] = {}
       self.config = config
       self.cwd = self.config.cwd
       

    def begin_streaming(self):
        self.console.print()
        self.console.print(Rule(Text("Assistance",style='assistant')))
        self.assistance_stream_open = True

    def print_welcome(self, title: str, lines: list[str]) -> None:
        body = "\n".join(lines)
        self.console.print(
            Panel(
                Text(body, style="code"),
                title=Text(title, style="highlight"),
                title_align="left",
                border_style="border",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )


    def _format_value(self,value):
        if isinstance(value, (dict, list)):
            return Text(json.dumps(value, indent=2), style="code")
        return Text(str(value), style="code")
    def stream_assistant_delta(self,content):
        self.console.print(content,end="",markup=False)
    def _ordered_arguments(self, tool_name: str, args: dict[str, Any]) -> list[tuple]:
        _preferred_order = {
        "read_file": ["path", "offset", "limit"],
        "write_file":["path",'create_directories',"content"],
        "edit":["path","replace_all","old_string","new_string"],
        "shell": ["command", "timeout", "cwd"],
        "list_dir":["path","include_hidden"],
        "grep":["path","case_insenstive","pattern"]
            }

        preferred = _preferred_order.get(tool_name, [])
        seen = set()
        ordered: list[Tuple[str, Any]] = []

        
        for key in preferred:
            if key in args:
                ordered.append((key, args[key]))
                seen.add(key)

    
        for key in args:
            if key not in seen:
                ordered.append((key, args[key]))

        return ordered

        
    def _render_argument_table(self,table_name:str,args:dict[str,Any])->Table:
        table = Table.grid(padding=(0,1))
        table.add_column(style="muted",justify="right",no_wrap=True)
        table.add_column(style="code",overflow="fold")

        for key , value in self._ordered_arguments(tool_name=table_name,args=args):
            if isinstance(value,str):
                if key in {"content","old_string","new_string"}:
                    line_count = len(value.splitlines()) or 0
                    byte_count = len(value.encode("utf-8",errors="replace")) or 0
                    value = f"{line_count} lines ⦁ {byte_count} bytes"
            table.add_row(str(key), self._format_value(value))
        return table


    def end_assistance(self):
        if self.assistance_stream_open:
            self.console.print()
        self.assistance_stream_open = False
    def render_tool_call_start(self,call_id,tool_kind:str,name:str,arguments:dict[str,Any])->None:
        self.tool_args_by_call_id[call_id] = arguments
        border_style = f"tool.{tool_kind}" if tool_kind else "tool"

        title = Text.assemble(
            ("⬤ ","muted"),
            (name,"tool"),
            (" ","muted"),
            (f"#{str(call_id or '')[:8]}","muted")
        )
        display_args = dict(arguments)
        for key in ("path","cwd"):
            val = display_args.get(key)
            if isinstance(val,str) and self.cwd:
                display_args[key] = str(display_path_relative_to_cwd(val,self.cwd))
        panel = Panel(
            self._render_argument_table(name,display_args) if display_args else Text("No arguments are present",style="muted"),
            title=title,
            title_align="left",
            subtitle=Text(f"running",style="muted"),
            subtitle_align='right',
            box=box.ROUNDED,
            padding=(1,2), 
        )
        self.console.print()
        self.console.print(panel)
    def _extract_read_file_code(self, text: str) -> tuple[int, Any] | None:
        body = text

        header_match = re.match(r"^Showing lines (\d+)-(\d+) of (\d+)\n\n", text)
        if header_match:
            body = text[header_match.end():]

        code_lines: list[str] = []
        start_line: int | None = None

        for line in body.splitlines():
            m = re.match(r"^\s*(\d+)\|(.*)$", line)
            if not m:
                continue  # skip instead of failing

            line_no = int(m.group(1))

            if start_line is None:
                start_line = line_no

            code_lines.append(m.group(2))

        if start_line is None:
            return None

        return start_line, "\n".join(code_lines)

    def render_tool_call_end(self, call_id, tool_kind: str, name: str, success: bool,error:str|None  = None, output: str | None = None, metadata: dict[str, Any] | None = None, diff: str | None = None, truncated: bool = False, exit_code: int | None = None) -> None:

        border_style = f"tool.{tool_kind}" if tool_kind else "tool"
        status_icon = "✅" if success else "❌"
        status_style = "success" if success else "error"
        args = self.tool_args_by_call_id.get(call_id, {})
        title = Text.assemble(
            (f"{status_icon}", status_style),
            (name, "tool"),
            (" ", "muted"),
            (f"#{str(call_id or '')[:8]}", "muted")
        )
        primary_path = None
        blocks = []
        if isinstance(metadata, dict) and isinstance(metadata.get("path"), str):
            primary_path = metadata.get("path")

        if name == "read_file" and success:
            if primary_path:
                start_line, code = self._extract_read_file_code(output)
                shown_starts = metadata.get("shown_start", "")
                shown_end = metadata.get("shown_end", "")
                total_lines = metadata.get("total_lines", "")
                pl = _guess_language(primary_path)
                blocks.append(Text())
                header_parts = [display_path_relative_to_cwd(primary_path, self.cwd)]
                header_parts.append(" ⦁ ")
                if shown_starts and shown_end and total_lines:
                    header_parts.append(f"lines {shown_starts}-{shown_end} of {total_lines}")
                header = "".join(header_parts)
                blocks.append(Text(header, style="muted"))
                blocks.append(Syntax(
                    code, pl, theme="monokai",
                    line_numbers=True, start_line=start_line, word_wrap=True
                ))
            else:
                output_display = truncate_text(output, "", 240)
                blocks.append(Syntax(output_display, "text", theme="monokai", word_wrap=False))

        elif name in {"write_file", "edit"} and success and diff:
            output_line = output.strip() if output.strip() else "completed"
            blocks.append(Text(output_line, style="muted"))
            diff_text = diff
            diff_display = truncate_text(diff_text, self.config.model_name, 240)
            blocks.append(Syntax(diff_display, "diff", theme='monokai', word_wrap=True))

        elif name == "shell" and success:
            command = args.get("command")
            if isinstance(command, str) and command.strip():
                blocks.append(Text(f"$ {command.strip()}", style="muted"))
            if exit_code is not None:
                blocks.append(Text(f"exit_code={exit_code}", style="muted"))
            shell_text = output or ""
            if not success and not shell_text:
                shell_text = "Shell command failed."
            output_display = truncate_text(shell_text, self.config.model_name, 240)
            if output_display.strip():
                blocks.append(Syntax(output_display, "text", theme="monokai", word_wrap=True))

        elif name == "grep" and success:
            matches = metadata.get("matches")
            files = metadata.get("files_searched")
            summary = []
            if isinstance(matches,int) :
                summary.append(f"no of matches {matches}")

            if isinstance(files,int) :
                summary.append(f"searched {files} files")

            if summary:
                 blocks.append(Text((" ⦁ ").join(summary),style='muted'))
                 blocks.append(Syntax(output,"text",theme="monokai",word_wrap=True))

        elif name == "glob" and success:
            matches = metadata.get("matches")
            summary = []
            if isinstance(matches,list) :
                summary.append(f"no of matches {len(matches)}")

            if summary:
                blocks.append(Text((" ⦁ ").join(summary),style='muted'))
                if output:
                    blocks.append(Syntax(output, "text", theme="monokai", word_wrap=True))
                else:
                    blocks.append(Text("No files matched.", style="muted"))

        elif name == "web_search" and success:
            lines = metadata.get("lines")
            query = metadata.get("query")
            summary = []
            if isinstance(lines,int) :
                summary.append(f"No of line in search {lines}")
            if isinstance(query,str) :
                summary.append(f" query for search{query}")


            if summary:
                blocks.append(Text((" ⦁ ").join(summary),style='muted'))
                if output:
                    blocks.append(Syntax(output, "text", theme="monokai", word_wrap=True))
                else:
                    blocks.append(Text("No files matched.", style="muted"))
        elif name == "web_fetch" and success:
            status_code = metadata.get("status_code")
            content_length = metadata.get("content_length")
            url = args.get("url")
            summary = []
            if isinstance(status_code, int):
                summary.append(str(status_code))
            if isinstance(content_length, int):
                summary.append(f"{content_length} bytes")
            if isinstance(url, str):
                summary.append(url)

            if summary:
                blocks.append(Text(" • ".join(summary), style="muted"))

            output_display = truncate_text(
                output,
                self.config.model_name,
                240
            )
            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )

        elif name == "todos" and success:
            output_display = truncate_text(
                output,
                self.config.model_name,
                400,
            )
            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )
        
        elif name == "memory" and success:
            action = args.get("action")
            key = args.get("key")
            found = metadata.get("found")
            summary = []
            if isinstance(action, str) and action:
                summary.append(action)
            if isinstance(key, str) and key:
                summary.append(key)
            if isinstance(found, bool):
                summary.append("found" if found else "missing")

            if summary:
                blocks.append(Text(" • ".join(summary), style="muted"))
            output_display = truncate_text(
                output,
                self.config.model_name,
                400,
            )
            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )

        elif name == "youtube_transcript" and success:
            video_id = metadata.get("video_id")
            length = metadata.get("length")

            summary = []

            if video_id:
                summary.append(f"Video ID: {video_id}")
            if length:
                summary.append(f"Length: {length} chars")

            if summary:
                blocks.append(Text(" ⦁ ".join(summary), style="muted"))

            display = output

            if display:
                blocks.append(
                    Syntax(display, "text", theme="monokai", word_wrap=True)
                )
            else:
                blocks.append(Text("No transcript found.", style="muted"))
                 



        elif name == "list_dir" and success:                                        
            listed_path = primary_path or args.get("path", ".")
            recursive   = metadata.get("recursive", False) if isinstance(metadata, dict) else args.get("recursive", False)
            total       = metadata.get("total_entries", "") if isinstance(metadata, dict) else ""
            is_truncated = metadata.get("truncated", False) if isinstance(metadata, dict) else False

            header_parts = [display_path_relative_to_cwd(listed_path, self.cwd)]
            if recursive:
                header_parts.append("  🌲 recursive")
            if total:
                header_parts.append(f"  ⦁  {total} entries")
            blocks.append(Text("".join(header_parts), style="muted"))

            if not success:
                # ── Error case ────────────────────────────────────────
                error_text = output or "list_dir failed."
                blocks.append(Text(error_text, style="error"))
            else:
                # ── Tree / flat output ────────────────────────────────
                dir_output = output or ""

                # Strip the trailing summary line before display
                # ("Total entries: N") — already shown in header
                lines = dir_output.splitlines()
                display_lines = [
                    l for l in lines
                    if not l.strip().startswith("Total entries:")
                ]
                dir_text = "\n".join(display_lines).strip()

                output_display = truncate_text(dir_text, self.config.model_name, 240)
                if output_display.strip():
                    blocks.append(Syntax(
                        output_display,
                        "text",
                        theme="monokai",
                        word_wrap=False,       
                    ))
                

                if is_truncated:
                    blocks.append(Text("⚠ listing truncated — use max_entries to increase limit", style="warning"))
        if error and not success:
                    blocks.append(Text(error,style="error"))
                    output_display = truncate_text(output,"gpt-4o-mini",240)
                    if output_display.strip():
                        blocks.append(Text(output_display,style="muted"))

        if truncated:
            blocks.append(Text("tool output was truncated", style="warning"))

        panel = Panel(
            Group(*blocks),
            title=title,
            title_align="left",
            subtitle=Text("done" if success else "failed", style=status_style),
            subtitle_align='right',
            box=box.ROUNDED,
            padding=(1, 2),
        )
        self.console.print()
        self.console.print(panel)
