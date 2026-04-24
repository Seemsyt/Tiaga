from __future__ import annotations

from pathlib import Path
from typing import Iterable

from tiaga.analysis.graph_builder import DependencyGraphBuilder


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20].rstrip() + "\n...(truncated)...\n"


def _top_k(items: Iterable[tuple[str, int]], k: int) -> list[tuple[str, int]]:
    sorted_items = sorted(items, key=lambda x: (-x[1], x[0]))
    return sorted_items[:k]


def build_project_graph_context(
    root_dir: Path,
    *,
    max_chars: int = 6000,
    max_tree_depth: int = 6,
    max_tree_children: int = 20,
    top_k: int = 8,
) -> str:
    """
    Returns a compact, module-level dependency overview for planner/executor prompts.

    Notes:
    - Best-effort; for Python we resolve imports -> project files.
    - Output is intentionally small to avoid drowning the LLM in noise.
    """
    root_dir = root_dir.resolve()
    builder = DependencyGraphBuilder(root_path=str(root_dir))
    builder.analyze_directory()

    edges = builder.get_module_edge_counts()
    out_degree: dict[str, int] = {}
    in_degree: dict[str, int] = {}
    for (src, dst), counts in edges.items():
        weight = sum(counts.values())
        if weight <= 0:
            continue
        out_degree[src] = out_degree.get(src, 0) + weight
        in_degree[dst] = in_degree.get(dst, 0) + weight

    tree = builder.to_tree(max_depth=max_tree_depth, max_children=max_tree_children).rstrip()

    lines: list[str] = []
    lines.append("# Project Graph (Auto-generated)")
    lines.append("Module-level dependency view (best effort; imports-based for Python).")
    lines.append("If you modify code structure, refresh this context by calling the tool: project_graph_refresh.")
    lines.append(f"Root: {root_dir}")
    lines.append("")
    lines.append("## Flow (tree)")
    lines.append(tree or "(no modules detected)")
    lines.append("")
    lines.append("## Hotspots")
    for label, degree_map in (
        ("Most incoming (depended on)", in_degree),
        ("Most outgoing (depends on others)", out_degree),
    ):
        lines.append(f"{label}:")
        items = _top_k(((m, c) for m, c in degree_map.items()), top_k)
        if not items:
            lines.append("- (none)")
        else:
            for module, count in items:
                lines.append(f"- {module} ({count})")
        lines.append("")

    return _truncate("\n".join(lines).rstrip() + "\n", max_chars=max_chars)
