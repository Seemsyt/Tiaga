import os
from pathlib import Path
import re

from pydantic import BaseModel
from pydantic import Field

from tiaga.context.text import truncate_text
from tiaga.tools_manager.base import Tool, Tool_kind, ToolInvocation, ToolResult
from tiaga.utils.path import resolve_path,is_binary


class GrepParams(BaseModel):
    pattern: str = Field(..., description="Regular expression pattern to search for")
    path: str = Field(
        ".", description="File or directory to search in (default: current directory)"
    )
    case_insensitive: bool = Field(
        False,
        description="Case-insensitive search (default: false)",
    )


class GrepTool(Tool):
    name = "grep"
    description = "Search for a regex pattern in file contents. Returns matching lines with file paths and line numbers."
    tool_kind = Tool_kind.READ
    schema = GrepParams


    def _find_files(self, search_path: Path) -> list[Path]:
        files = []

        for root, dirs, filenames in os.walk(search_path):
            dirs[:] = [
                d
                for d in dirs
                if d not in {"node_modules", "__pycache__", ".git", ".venv", "venv"}
            ]

            for filename in filenames:
                if filename.startswith("."):
                    continue

                file_path = Path(root) / filename
                if not is_binary(file_path):
                    files.append(file_path)
                    if len(files) >= 500:
                        return files

        return files

    async def execute(self, invocation: ToolInvocation):
        params = GrepParams(**invocation.params)
        search_path = resolve_path(invocation.cwd, params.path)

        if not search_path.exists():
            return ToolResult.error_result(f"Path not found: {search_path}")

        try:
            flags = re.IGNORECASE if params.case_insensitive else 0
            pattern = re.compile(params.pattern, flags)
        except re.error as e:
            return ToolResult.error_result(f"Invalid regex pattern: {e}")

        if search_path.is_dir():
            files = self._find_files(search_path)
        else:
            if is_binary(search_path):
                return ToolResult.error_result("Cannot search in binary file")
            files = [search_path]

        output_lines = []
        matches = 0

        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            lines = content.splitlines()
            file_matches = False

            for i, line in enumerate(lines, start=1):
                if pattern.search(line):
                    matches += 1
                    if not file_matches:
                        rel_path = file_path.relative_to(invocation.cwd)
                        output_lines.append(f"=== {rel_path} ===")
                        file_matches = True

                    output_lines.append(f"{i}:{line}")

            if file_matches:
                output_lines.append("")

        if not output_lines:
            return ToolResult.success_result(
                f"No matches found for pattern '{params.pattern}'",
                metadata={
                    "path": str(search_path),
                    "matches": 0,
                    "files_searched": len(files),
                },
            )

        output = "\n".join(output_lines)

        display_output = None
        is_truncated = False

        maybe_truncated = truncate_text(
            output,
            model="gpt-4o-mini",
            max_tokens=240,
            suffix="\n...[truncated for display]",
        )

        if maybe_truncated != output:
            display_output = maybe_truncated
            is_truncated = True

        return ToolResult.success_result(
            output=output,
            display_output=display_output,
            truncated=is_truncated,
            metadata={
                "path": str(search_path),
                "matches": matches,
                "files_searched": len(files),
            },
        )
            




        
        
