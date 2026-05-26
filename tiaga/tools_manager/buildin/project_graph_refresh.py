from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from tiaga.analysis.graph_builder import DependencyGraphBuilder
from tiaga.analysis.project_graph_context import build_project_graph_context
from tiaga.config.config import Config
from tiaga.tools_manager.base import Tool, ToolInvocation, ToolResult, Tool_kind


class ProjectGraphRefreshInput(BaseModel):
    directory: str = Field(default=".", description="Directory to analyze (relative to cwd)")
    formats: list[str] = Field(
        default_factory=lambda: ["tree", "md", "summary"],
        description="Any of: tree, md, summary, dot, json",
    )
    max_context_chars: int = Field(
        default=6000,
        ge=500,
        le=50000,
        description="Max characters of graph context returned to the model",
    )


class ProjectGraphRefreshTool(Tool):
    name = "project_graph_refresh"
    description = "Rebuild and save project dependency graphs under ./project_graph and return refreshed graph context for the agent."
    tool_kind = Tool_kind.WRITE
    schema = ProjectGraphRefreshInput

    def __init__(self, config: Config):
        super().__init__(config)

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        base_dir = invocation.cwd.resolve()
        params = ProjectGraphRefreshInput(**(invocation.params or {}))

        target_dir = Path(params.directory)
        if not target_dir.is_absolute():
            target_dir = base_dir / target_dir
        target_dir = target_dir.resolve()
        if not target_dir.exists():
            return ToolResult.error_result(f"Directory not found: {params.directory}")

        out_dir = base_dir / "project_graph"
        out_dir.mkdir(parents=True, exist_ok=True)

        builder = DependencyGraphBuilder(root_path=str(target_dir))
        builder.analyze_directory()
        builder.find_cycles()

        written: dict[str, str] = {}
        for fmt in params.formats:
            fmt = (fmt or "").strip().lower()
            if fmt == "tree":
                content = builder.to_tree()
                ext = "tree"
            elif fmt == "md":
                content = builder.to_markdown()
                ext = "md"
            elif fmt == "summary":
                content = builder.get_summary()
                ext = "summary"
            elif fmt == "dot":
                content = builder.to_dot()
                ext = "dot"
            elif fmt == "json":
                content = builder.to_json()
                ext = "json"
            else:
                return ToolResult.error_result(f"Unsupported format: {fmt}")

            path = out_dir / f"project_graph.{ext}"
            path.write_text(content, encoding="utf-8")
            written[fmt] = str(path)

        # Also provide a compact context snapshot the agent can use immediately.
        context = build_project_graph_context(target_dir, max_chars=params.max_context_chars)

        return ToolResult.success_result(
            output=(
                "Project graph refreshed.\n"
                + "\n".join([f"- {k}: {v}" for k, v in sorted(written.items())])
            ),
            metadata={"written": written, "project_graph_context": context},
        )

