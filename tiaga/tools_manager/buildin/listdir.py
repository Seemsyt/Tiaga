import os
import stat
from pathlib import Path
from pydantic import BaseModel, Field

from tiaga.context.text import truncate_text
from tiaga.tools_manager.base import Tool, ToolInvocation, ToolResult, Tool_kind
from tiaga.utils.path import resolve_path


class ListDirParams(BaseModel):
    path: str = Field(".", description="Directory path to list (default: current directory)")
    include_hidden: bool = Field(False, description="Whether to include hidden files and directories (default: false)")
    recursive: bool = Field(False, description="Whether to list recursively like a tree (default: false)")
    max_depth: int = Field(3, ge=1, le=10, description="Max recursion depth when recursive=true (default: 3)")
    max_entries: int = Field(1000, ge=1, le=10000, description="Max total entries to return (default: 1000)")


class ListDir(Tool):
    name = "list_dir"
    description = (
        "List contents of a directory. Supports recursive tree view, "
        "hidden files, symlinks, and depth control."
    )
    tool_kind = Tool_kind.READ
    schema = ListDirParams
    MAX_DISPLAY_OUTPUT_TOKENS = 25000

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = ListDirParams(**invocation.params)

        # ── Resolve path ──────────────────────────────────────────────
        try:
            dir_path = resolve_path(invocation.cwd, params.path)
        except Exception as e:
            return ToolResult.error_result(f"Invalid path: {e}")

        # ── Existence & type checks ───────────────────────────────────
        if not dir_path.exists():
            return ToolResult.error_result(f"Path does not exist: {dir_path}")

        if dir_path.is_symlink() and not dir_path.exists():
            return ToolResult.error_result(f"Broken symlink: {dir_path}")

        if not dir_path.is_dir():
            return ToolResult.error_result(f"Path is not a directory: {dir_path}")

        # ── Permission check ──────────────────────────────────────────
        if not os.access(dir_path, os.R_OK):
            return ToolResult.error_result(f"Permission denied: {dir_path}")

        # ── Build output ──────────────────────────────────────────────
        counter = {"total": 0, "truncated": False}

        try:
            if params.recursive:
                lines = [str(dir_path)]
                self._build_tree(
                    path=dir_path,
                    lines=lines,
                    prefix="",
                    depth=0,
                    params=params,
                    counter=counter,
                )
                output = "\n".join(lines)
            else:
                output = self._flat_list(dir_path, params, counter)
        except PermissionError as e:
            return ToolResult.error_result(f"Permission denied while reading: {e}")
        except OSError as e:
            return ToolResult.error_result(f"OS error while reading directory: {e}")

        # ── Append summary ────────────────────────────────────────────
        summary = f"\n\nTotal entries: {counter['total']}"
        if counter["truncated"]:
            summary += f" (truncated at {params.max_entries})"

        full_output = output + summary
        display_output = truncate_text(
            full_output,
            model="gpt-4o-mini",
            max_tokens=self.MAX_DISPLAY_OUTPUT_TOKENS,
            suffix="\n...[truncated for display]",
        )
        display_truncated = display_output != full_output

        return ToolResult(
            success=True,
            output=full_output,
            display_output=display_output if display_truncated else None,
            truncated=display_truncated,
            metadata={
                "path": str(dir_path),
                "total_entries": counter["total"],
                "truncated": counter["truncated"],
                "recursive": params.recursive,
            }
        )

    # ── Flat list (non-recursive) ─────────────────────────────────────
    def _flat_list(self, path: Path, params: ListDirParams, counter: dict) -> str:
        entries = self._get_entries(path, params.include_hidden)
        lines = [f"{path}/"]

        for entry in entries:
            if counter["total"] >= params.max_entries:
                counter["truncated"] = True
                break

            label = self._format_entry(entry, path)
            lines.append(f"  {label}")
            counter["total"] += 1

        if not entries:
            lines.append("  (empty directory)")

        return "\n".join(lines)

    # ── Recursive tree ────────────────────────────────────────────────
    def _build_tree(
        self,
        path: Path,
        lines: list[str],
        prefix: str,
        depth: int,
        params: ListDirParams,
        counter: dict,
    ) -> None:
        if depth >= params.max_depth:
            lines.append(f"{prefix}... (max depth {params.max_depth} reached)")
            return

        if counter["truncated"]:
            return

        entries = self._get_entries(path, params.include_hidden)

        for i, entry in enumerate(entries):
            if counter["total"] >= params.max_entries:
                counter["truncated"] = True
                lines.append(f"{prefix}... (truncated at {params.max_entries} entries)")
                return

            is_last = (i == len(entries) - 1)
            connector = "└── " if is_last else "├── "
            child_prefix = prefix + ("    " if is_last else "│   ")

            label = self._format_entry(entry, path)
            lines.append(f"{prefix}{connector}{label}")
            counter["total"] += 1

            # Recurse into directories (but not symlinked dirs to avoid loops)
            if entry.is_dir():
                self._build_tree(
                    path=entry,
                    lines=lines,
                    prefix=child_prefix,
                    depth=depth + 1,
                    params=params,
                    counter=counter,
                )
            elif entry.is_symlink():
                # Show symlink target
                try:
                    target = os.readlink(entry)
                    resolved = entry.resolve()
                    broken = not resolved.exists()
                    tag = f" -> {target}" + (" [BROKEN]" if broken else "")
                    # Patch the last line to append symlink info
                    lines[-1] = lines[-1] + tag
                except OSError:
                    lines[-1] = lines[-1] + " -> [unreadable symlink]"

    # ── Helpers ───────────────────────────────────────────────────────
    def _get_entries(self, path: Path, include_hidden: bool) -> list[Path]:
        """Return sorted directory entries: dirs first, then files."""
        try:
            entries = list(path.iterdir())
        except PermissionError:
            return []

        if not include_hidden:
            entries = [e for e in entries if not e.name.startswith(".")]

        # Dirs first, then files — both sorted alphabetically
        dirs = sorted([e for e in entries if e.is_dir()])
        files = sorted([e for e in entries if not e.is_dir()])
        return dirs + files

    def _format_entry(self, entry: Path, parent: Path) -> str:
        """Format a single entry with type indicators and metadata."""
        name = entry.name

        # Type suffix
        if entry.is_symlink():
            suffix = "@"  # symlink
        elif entry.is_dir():
            suffix = "/"  # directory
        elif self._is_executable(entry):
            suffix = "*"  # executable
        else:
            suffix = ""

        # File size for files
        meta = ""
        if entry.is_file():
            try:
                size = entry.stat().st_size
                meta = f"  ({self._human_size(size)})"
            except OSError:
                meta = "  (?)"

        return f"{name}{suffix}{meta}"

    @staticmethod
    def _is_executable(path: Path) -> bool:
        try:
            return os.access(path, os.X_OK) and path.is_file()
        except OSError:
            return False

    @staticmethod
    def _human_size(size: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
        
        
