
import os
from pathlib import Path

from pydantic import BaseModel
from pydantic import Field

from tiaga.context.text import truncate_text
from tiaga.tools_manager.base import Tool, Tool_kind, ToolInvocation, ToolResult
from tiaga.utils.path import resolve_path,is_binary


class GlobParams(BaseModel):
    pattern: str = Field(..., description="Glob pattern to match for (eg. **/*.ts)")
    path: str = Field(
        ".", description="Directory to search in (default: current directory)"
    )
    


class GlobTool(Tool):
    name = "glob"
    description = "Find files matching glob patterns. Supports ** for recursive search."
    tool_kind = Tool_kind.READ
    schema = GlobParams


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
        params = GlobParams(**invocation.params)
        search_path = resolve_path(invocation.cwd, params.path)

        if not search_path.exists() or not search_path.is_dir():
            return ToolResult.error_result(f"Directory not found: {search_path}")

        try:
            all_files = self._find_files(search_path)
            matches = [
                    p for p in all_files if p.match(params.pattern)]
        except Exception as e:
            return ToolResult.error_result(f"Error during searching: {e}")

        output_lines = []


        for file_path in matches[:5000]:
            try:
                rel_path = file_path.relative_to(invocation.cwd)
            except Exception:
                rel_path = file_path

            output_lines.append(str(rel_path))

            
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
                "matches": [str(p) for p in matches]
            },
        )
            




        
        
