"""Multi-language dependency graph builder.

Supports: Python, JavaScript, TypeScript, Java, Go, Rust, C, C++
"""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict, deque
import re
import posixpath

from tiaga.analysis.language_parsers import (
    get_parser,
    SUPPORTED_LANGUAGES,
    ExtractedDefinition,
    ExtractedDependency,
)


@dataclass
class GraphNode:
    """Represents a node in the dependency graph."""
    id: str  # "module.py::ClassName::method_name"
    name: str  # "method_name"
    type: str  # "function", "class", "method"
    module: str  # "module.py"
    lineno: int

    def to_dict(self):
        return asdict(self)


@dataclass
class GraphEdge:
    """Represents an edge in the dependency graph."""
    source: str  # node id
    target: str  # node id
    edge_type: str  # "calls", "imports", "inherits"
    is_cycle: bool = False

    def to_dict(self):
        return asdict(self)


class DefinitionConverter:
    """Converts parsed definitions to graph nodes and edges."""

    def __init__(self, module_name: str):
        self.module_name = module_name
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[Tuple[str, str, str]] = []

    def add_definition(self, definition: ExtractedDefinition) -> str:
        """Convert definition to graph node and return full ID."""
        scope_str = "::".join(definition.scope)
        if scope_str:
            full_id = f"{self.module_name}::{scope_str}::{definition.name}"
        else:
            full_id = f"{self.module_name}::{definition.name}"

        self.nodes[full_id] = GraphNode(
            id=full_id,
            name=definition.name,
            type=definition.type,
            module=self.module_name,
            lineno=definition.lineno,
        )
        return full_id

    def add_dependency(self, dep: ExtractedDependency) -> None:
        """Convert dependency to graph edge."""
        source_id = self._resolve_id(dep.source)
        target_id = self._resolve_id(dep.target)
        if source_id and target_id:
            self.edges.append((source_id, target_id, dep.dep_type))

    def _resolve_id(self, name: str) -> Optional[str]:
        """Resolve a dependency name to full ID."""
        # If it's already a full ID (contains ::), return it
        if "::" in name:
            return name
        # Otherwise, make it module-qualified
        return f"{self.module_name}::{name}"


class DependencyGraphBuilder:
    """Builds and analyzes dependency graphs for multi-language codebases."""

    def __init__(self, root_path: str = "."):
        self.root_path = Path(root_path)
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[GraphEdge] = []
        self.cycles: List[List[str]] = []
        self.languages_found: Set[str] = set()
        self._module_edge_counts: Dict[Tuple[str, str], Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._all_files_rel: Set[str] = set()

        # Per-language indices for best-effort import->file resolution.
        self._py_module_to_file: Dict[str, str] = {}
        self._py_file_to_module: Dict[str, str] = {}
        self._java_class_to_file: Dict[str, str] = {}
        self._go_module_path: str | None = None
        self._go_pkg_dir_to_file: Dict[str, str] = {}
        self._c_rel_files: Set[str] = set()
        self._rust_mod_to_file: Dict[str, str] = {}
        self._rust_file_to_mod: Dict[str, str] = {}

    def analyze_file(self, file_path: Path) -> None:
        """Analyze a single source file."""
        parser = get_parser(file_path)
        if not parser:
            return  # Unsupported file type

        self.languages_found.add(parser.LANGUAGE_NAME)

        try:
            # Ensure parser uses a stable module name relative to root_path.
            try:
                parser.module_name = str(file_path.relative_to(self.root_path))
            except Exception:
                parser.module_name = str(file_path)

            definitions, dependencies = parser.parse()
            
            # Convert definitions to graph nodes
            converter = DefinitionConverter(str(file_path.relative_to(self.root_path)))
            for definition in definitions:
                converter.add_definition(definition)

            # Convert dependencies to graph edges (and module-level edges for imports)
            for dependency in dependencies:
                if dependency.dep_type == "imports":
                    self._record_module_import(converter.module_name, dependency.target)
                else:
                    converter.add_dependency(dependency)

            # Merge into main graph
            self.nodes.update(converter.nodes)
            for source, target, edge_type in converter.edges:
                self.edges.append(GraphEdge(source, target, edge_type))

        except Exception as e:
            print(f"Warning: Error analyzing {file_path}: {e}")

    def _is_skipped_path(self, file_path: Path) -> bool:
        return any(
            part in file_path.parts
            for part in [
                "__pycache__",
                ".venv",
                "venv",
                "env",
                ".egg-info",
                "node_modules",
                ".git",
                ".github",
                ".idea",
                ".vscode",
                ".seems-tiaga",
                "project_graph",
                "dist",
                "build",
                "out",
                "coverage",
                ".cache",
                ".pytest_cache",
                ".mypy_cache",
                ".ruff_cache",
                ".tox",
                ".nuxt",
                ".next",
                ".svelte-kit",
                ".angular",
                ".output",
                ".turbo",
                ".pnpm",
                ".yarn",
                "target",
            ]
        )

    def _build_python_module_index(self, search_path: Path) -> None:
        self._py_module_to_file = {}
        self._py_file_to_module = {}
        for file_path in search_path.rglob("*.py"):
            if self._is_skipped_path(file_path):
                continue
            try:
                rel = str(file_path.relative_to(self.root_path))
            except Exception:
                continue
            rel_path = Path(rel)
            if rel_path.name == "__init__.py":
                rel_no_suffix = rel_path.parent
            else:
                rel_no_suffix = rel_path.with_suffix("")

            parts = list(rel_no_suffix.parts)
            if not parts:
                continue
            if any(not p.isidentifier() for p in parts):
                continue
            mod = ".".join(parts)
            self._py_module_to_file[mod] = rel
            self._py_file_to_module[rel] = mod
            if rel_path.name == "__init__.py":
                # Also map package name to __init__.py
                self._py_module_to_file[mod] = rel

    def _build_java_index(self, files: list[Path]) -> None:
        self._java_class_to_file = {}
        pkg_re = re.compile(r"^\s*package\s+([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*)\s*;")
        for file_path in files:
            if file_path.suffix.lower() != ".java":
                continue
            if self._is_skipped_path(file_path):
                continue
            try:
                rel = str(file_path.relative_to(self.root_path))
            except Exception:
                continue
            try:
                head = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()[:60]
            except OSError:
                continue
            package = ""
            for line in head:
                m = pkg_re.match(line)
                if m:
                    package = m.group(1)
                    break
            class_name = file_path.stem
            if package:
                key = f"{package}.{class_name}"
            else:
                key = class_name
            self._java_class_to_file[key] = rel

    def _build_go_index(self, files: list[Path], search_path: Path) -> None:
        self._go_pkg_dir_to_file = {}
        self._go_module_path = None

        go_mod = None
        for candidate in [search_path / "go.mod", self.root_path / "go.mod"]:
            if candidate.is_file():
                go_mod = candidate
                break
        if go_mod:
            try:
                for line in go_mod.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if line.startswith("module "):
                        self._go_module_path = line.split(None, 1)[1].strip()
                        break
            except OSError:
                pass

        for file_path in files:
            if file_path.suffix.lower() != ".go":
                continue
            if self._is_skipped_path(file_path):
                continue
            try:
                rel = str(file_path.relative_to(self.root_path))
            except Exception:
                continue
            dir_rel = str(Path(rel).parent)
            # Use one representative file per package dir.
            self._go_pkg_dir_to_file.setdefault(dir_rel, rel)

    def _build_c_index(self, files: list[Path]) -> None:
        self._c_rel_files = set()
        for file_path in files:
            if file_path.suffix.lower() not in {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp"}:
                continue
            if self._is_skipped_path(file_path):
                continue
            try:
                rel = str(file_path.relative_to(self.root_path))
            except Exception:
                continue
            self._c_rel_files.add(rel)

    def _build_rust_index(self, files: list[Path]) -> None:
        self._rust_mod_to_file = {}
        self._rust_file_to_mod = {}

        def file_to_mod(rel: str) -> str | None:
            rel_path = Path(rel)
            parts = list(rel_path.parts)
            if "src" not in parts:
                return None
            src_index = parts.index("src")
            tail = parts[src_index + 1 :]
            if not tail:
                return None
            if rel_path.name in ("lib.rs", "main.rs"):
                return "crate"
            if rel_path.name == "mod.rs":
                mod_parts = tail[:-1]  # drop mod.rs
            else:
                mod_parts = list(Path(*tail).with_suffix("").parts)
            if not mod_parts:
                return "crate"
            return "crate::" + "::".join(mod_parts)

        for file_path in files:
            if file_path.suffix.lower() != ".rs":
                continue
            if self._is_skipped_path(file_path):
                continue
            try:
                rel = str(file_path.relative_to(self.root_path))
            except Exception:
                continue
            mod = file_to_mod(rel)
            if not mod:
                continue
            self._rust_mod_to_file[mod] = rel
            self._rust_file_to_mod[rel] = mod

    def _build_file_indices(self, search_path: Path) -> None:
        # Collect all supported files first (so resolution can happen while parsing).
        supported_exts: Set[str] = set()
        for exts in SUPPORTED_LANGUAGES.values():
            supported_exts.update(exts)

        files: list[Path] = []
        self._all_files_rel = set()
        
        # Initialize to empty list to ensure attribute always exists
        self._all_supported_files = []
        
        try:
            for ext in supported_exts:
                for file_path in search_path.rglob(f"*{ext}"):
                    if self._is_skipped_path(file_path):
                        continue
                    files.append(file_path)
                    try:
                        rel = str(file_path.relative_to(self.root_path))
                        self._all_files_rel.add(rel)
                    except Exception:
                        pass
        except Exception as e:
            import warnings
            warnings.warn(f"Error during file discovery: {e}", UserWarning)

        # Build per-language indices (with error handling).
        try:
            self._build_python_module_index(search_path)
        except Exception as e:
            import warnings
            warnings.warn(f"Error building Python index: {e}", UserWarning)
            
        try:
            self._build_java_index(files)
        except Exception as e:
            import warnings  
            warnings.warn(f"Error building Java index: {e}", UserWarning)
            
        try:
            self._build_go_index(files, search_path)
        except Exception as e:
            import warnings
            warnings.warn(f"Error building Go index: {e}", UserWarning)
            
        try:
            self._build_c_index(files)
        except Exception as e:
            import warnings
            warnings.warn(f"Error building C index: {e}", UserWarning)
            
        try:
            self._build_rust_index(files)
        except Exception as e:
            import warnings
            warnings.warn(f"Error building Rust index: {e}", UserWarning)

        self._all_supported_files = files

    def _resolve_python_import(self, src_module_file: str, import_target: str) -> str | None:
        # Handles "pkg.mod" and relative imports like ".utils" / "..core".
        if not import_target:
            return None

        dotted = import_target.strip()
        if dotted.startswith("."):
            level = len(dotted) - len(dotted.lstrip("."))
            module_part = dotted[level:]  # may be ""
            src_dotted = self._py_file_to_module.get(src_module_file)
            if not src_dotted:
                return None
            # In Python, relative import level is relative to the current package.
            src_parts = src_dotted.split(".")
            if src_module_file.endswith("/__init__.py") or src_module_file.endswith("\\__init__.py") or src_module_file.endswith("__init__.py"):
                pkg_parts = src_parts
            else:
                pkg_parts = src_parts[:-1]
            for _ in range(max(level - 1, 0)):
                if pkg_parts:
                    pkg_parts = pkg_parts[:-1]
            base_pkg = ".".join(pkg_parts)
            dotted = f"{base_pkg}.{module_part}".strip(".") if module_part else base_pkg

        if not dotted:
            return None

        if dotted in self._py_module_to_file:
            return self._py_module_to_file[dotted]
        init_key = f"{dotted}.__init__"
        if init_key in self._py_module_to_file:
            return self._py_module_to_file[init_key]
        return None

    def _resolve_js_ts_import(self, src_module_file: str, import_target: str) -> str | None:
        target = (import_target or "").strip()
        if not target:
            return None
        if not (target.startswith(".") or target.startswith("/")):
            return None  # external/bare specifier

        src_path = Path(src_module_file)
        if target.startswith("/"):
            base = Path(target.lstrip("/"))
        else:
            base = (src_path.parent / target)

        # Normalize without resolving against filesystem.
        base = Path(posixpath.normpath(base.as_posix()))

        exts = [".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".vue"]
        candidates: list[Path] = []
        if base.suffix:
            candidates.append(base)
        else:
            for ext in exts:
                candidates.append(Path(str(base) + ext))
            for ext in exts:
                candidates.append(base / f"index{ext}")

        for cand in candidates:
            rel = posixpath.normpath(cand.as_posix())
            if rel in self._all_files_rel:
                return rel
        return None

    def _resolve_java_import(self, import_target: str) -> str | None:
        target = (import_target or "").strip()
        if not target or target.endswith(".*"):
            return None
        return self._java_class_to_file.get(target)

    def _resolve_go_import(self, import_target: str) -> str | None:
        target = (import_target or "").strip()
        if not target:
            return None

        candidate = None
        if self._go_module_path and (target == self._go_module_path or target.startswith(self._go_module_path + "/")):
            candidate = target[len(self._go_module_path):].lstrip("/")

        if candidate is None:
            return None

        candidate = candidate.strip("/")
        if not candidate:
            return None

        if candidate in self._go_pkg_dir_to_file:
            return self._go_pkg_dir_to_file[candidate]

        matches = [d for d in self._go_pkg_dir_to_file.keys() if d.endswith(candidate)]
        if len(matches) == 1:
            return self._go_pkg_dir_to_file[matches[0]]
        return None

    def _resolve_c_include(self, import_target: str) -> str | None:
        target = (import_target or "").strip()
        if not target:
            return None

        # Direct match
        if target in self._c_rel_files:
            return target

        # Suffix match (e.g. "dir/foo.h" in include)
        suffix = target.lstrip("./")
        matches = [p for p in self._c_rel_files if p.endswith("/" + suffix) or p == suffix]
        if len(matches) == 1:
            return matches[0]

        # Basename match as last resort.
        base = Path(target).name
        matches = [p for p in self._c_rel_files if Path(p).name == base]
        if len(matches) == 1:
            return matches[0]
        return None

    def _resolve_rust_import(self, src_module_file: str, import_target: str) -> str | None:
        raw = (import_target or "").strip()
        if not raw:
            return None
        # Strip common "pub " prefixes and brace groups.
        raw = raw.removeprefix("pub ").strip()
        raw = raw.split("{", 1)[0].strip().rstrip(":").rstrip()
        raw = raw.rstrip(":").rstrip()
        raw = raw.rstrip("::")

        if not raw:
            return None

        src_mod = self._rust_file_to_mod.get(src_module_file, "crate")

        # Resolve relative prefixes.
        def resolve_relative(path: str) -> str:
            cur_mod = src_mod
            while path.startswith("super::"):
                if "::" in cur_mod:
                    cur_mod = cur_mod.rsplit("::", 1)[0]
                path = path[len("super::"):]
            if path.startswith("self::"):
                path = path[len("self::"):]
            if not path:
                return cur_mod
            if cur_mod == "crate":
                return f"crate::{path}"
            return f"{cur_mod}::{path}"

        candidates: list[str] = []
        if raw.startswith("crate::") or raw == "crate":
            candidates.append(raw)
        elif raw.startswith("self::") or raw.startswith("super::"):
            candidates.append(resolve_relative(raw))
        else:
            # Try treating it as crate-local first.
            candidates.append(f"crate::{raw}")

        for key in candidates:
            if key in self._rust_mod_to_file:
                return self._rust_mod_to_file[key]
        return None

    def _resolve_import_to_file(self, src_module_file: str, import_target: str) -> str | None:
        suffix = Path(src_module_file).suffix.lower()
        if suffix == ".py":
            return self._resolve_python_import(src_module_file, import_target)
        if suffix in {".js", ".jsx", ".ts", ".tsx"}:
            return self._resolve_js_ts_import(src_module_file, import_target)
        if suffix == ".java":
            return self._resolve_java_import(import_target)
        if suffix == ".go":
            return self._resolve_go_import(import_target)
        if suffix == ".rs":
            return self._resolve_rust_import(src_module_file, import_target)
        if suffix in {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp"}:
            return self._resolve_c_include(import_target)
        return None

    def _record_module_import(self, src_module_file: str, import_target: str) -> None:
        resolved = self._resolve_import_to_file(src_module_file, import_target)
        if not resolved:
            return
        if resolved == src_module_file:
            return
        self._module_edge_counts[(src_module_file, resolved)]["imports"] += 1

    def analyze_directory(self, target_dir: Optional[str] = None) -> None:
        """Analyze all supported source files in a directory."""
        if target_dir:
            search_path = self.root_path / target_dir
        else:
            search_path = self.root_path

        # Build indices up-front so imports can be resolved to project files.
        # Ensure search_path exists before building indices
        if not search_path.exists():
            raise FileNotFoundError(f"Search path does not exist: {search_path}")
        
        self._build_file_indices(search_path)

        # Use _all_supported_files if it was set, otherwise raise error
        if not hasattr(self, "_all_supported_files"):
            raise RuntimeError("File discovery failed: _all_supported_files not set. Check _build_file_indices.")
        
        # Log warning if no files found
        if not self._all_supported_files:
            import warnings
            warnings.warn(f"No supported source files found in {search_path}", UserWarning)
            return
        
        for file_path in self._all_supported_files:
            try:
                self.analyze_file(file_path)
            except Exception as e:
                # Continue analyzing other files even if one fails
                import warnings
                warnings.warn(f"Failed to analyze {file_path}: {e}", UserWarning)

    def find_cycles(self) -> List[List[str]]:
        """Find circular dependencies using DFS."""
        if self.cycles:
            return self.cycles

        # Build adjacency list
        graph: Dict[str, List[str]] = defaultdict(list)
        for edge in self.edges:
            if edge.edge_type in ["calls", "imports"]:
                graph[edge.source].append(edge.target)

        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        cycles: List[List[str]] = []

        def dfs(node: str, path: List[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)

            path.pop()
            rec_stack.remove(node)

        for node in graph:
            if node not in visited:
                dfs(node, [])

        self.cycles = cycles

        # Mark edges that are part of cycles
        cycle_pairs: Set[Tuple[str, str]] = set()
        for cycle in cycles:
            for i in range(len(cycle) - 1):
                cycle_pairs.add((cycle[i], cycle[i + 1]))

        for edge in self.edges:
            if (edge.source, edge.target) in cycle_pairs:
                edge.is_cycle = True

        return cycles

    def to_dict(self) -> dict:
        """Convert graph to dictionary format."""
        return {
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges],
            "cycles": self.cycles,
            "stats": {
                "total_nodes": len(self.nodes),
                "total_edges": len(self.edges),
                "total_cycles": len(self.cycles),
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert graph to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_dot(self) -> str:
        """Convert graph to Graphviz DOT format."""
        lines = ["digraph DependencyGraph {"]
        lines.append('  rankdir="LR";')
        lines.append('  node [shape=box];')

        # Add nodes
        for node in self.nodes.values():
            label = f"{node.name}\\n({node.type})"
            lines.append(f'  "{node.id}" [label="{label}"];')

        # Add edges
        for edge in self.edges:
            color = "red" if edge.is_cycle else "black"
            style = "bold" if edge.is_cycle else "solid"
            lines.append(f'  "{edge.source}" -> "{edge.target}" [color="{color}", style="{style}"];')

        lines.append("}")
        return "\n".join(lines)

    def _module_from_full_id(self, full_id: str) -> str:
        # Node IDs are built as "<module>::<scope...>::<name>".
        # Fall back to the full id if unexpected.
        if "::" not in full_id:
            return full_id
        return full_id.split("::", 1)[0]

    def to_mermaid(self) -> str:
        """Convert graph to a high-level Mermaid flowchart (module-level)."""
        modules = sorted(self.get_modules())
        module_ids = {module: f"m{idx}" for idx, module in enumerate(modules)}

        def _label(text: str) -> str:
            return text.replace('"', "'").replace("\n", " ").strip()

        lines: List[str] = ["flowchart LR"]
        for module in modules:
            lines.append(f'  {module_ids[module]}["{_label(module)}"]')

        for (src_mod, dst_mod), counts_by_type in sorted(self.get_module_edge_counts().items()):
            label_parts = []
            for edge_type in sorted(counts_by_type.keys()):
                label_parts.append(f"{edge_type}:{counts_by_type[edge_type]}")
            label = ", ".join(label_parts)
            if label:
                lines.append(f"  {module_ids[src_mod]} -->|{label}| {module_ids[dst_mod]}")
            else:
                lines.append(f"  {module_ids[src_mod]} --> {module_ids[dst_mod]}")

        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Markdown report with an embedded Mermaid diagram and concise flow stats."""
        # Module-level degree counts for quick orientation.
        out_degree: Dict[str, int] = defaultdict(int)
        in_degree: Dict[str, int] = defaultdict(int)
        for (src_mod, dst_mod), counts in self.get_module_edge_counts().items():
            weight = sum(counts.values())
            if weight <= 0:
                continue
            out_degree[src_mod] += weight
            in_degree[dst_mod] += weight

        modules = sorted(set(out_degree.keys()) | set(in_degree.keys()))
        top_out = sorted(modules, key=lambda m: (-out_degree.get(m, 0), m))[:10]
        top_in = sorted(modules, key=lambda m: (-in_degree.get(m, 0), m))[:10]

        lines: List[str] = []
        lines.append("# Dependency Graph")
        lines.append("")
        lines.append("## Overview")
        lines.append(f"- Total nodes: {len(self.nodes)}")
        lines.append(f"- Total edges: {len(self.edges)}")
        if self.languages_found:
            lines.append(f"- Languages: {', '.join(sorted(self.languages_found))}")
        lines.append("")
        lines.append("## Diagram (module-level)")
        lines.append("```mermaid")
        lines.append(self.to_mermaid())
        lines.append("```")
        lines.append("")
        lines.append("## Hotspots")
        lines.append("")
        lines.append("### Most outgoing dependencies")
        for module in top_out:
            lines.append(f"- {module} ({out_degree.get(module, 0)})")
        lines.append("")
        lines.append("### Most incoming dependencies")
        for module in top_in:
            lines.append(f"- {module} ({in_degree.get(module, 0)})")
        lines.append("")
        lines.append("## Cycles")
        cycles = self.find_cycles()
        lines.append(f"- Circular dependencies found: {len(cycles)}")
        if cycles:
            lines.append("")
            lines.append("### Examples (node-level)")
            for i, cycle in enumerate(cycles[:5], 1):
                cycle_str = " -> ".join([node.split("::")[-1] for node in cycle])
                lines.append(f"- {i}. {cycle_str}")
        lines.append("")
        return "\n".join(lines)

    def get_modules(self) -> Set[str]:
        modules: Set[str] = set()
        for node in self.nodes.values():
            modules.add(node.module)
        for (src_mod, dst_mod) in self._module_edge_counts.keys():
            modules.add(src_mod)
            modules.add(dst_mod)
        return modules

    def get_module_edge_counts(self) -> Dict[Tuple[str, str], Dict[str, int]]:
        """Module-level edge counts keyed by (src_module, dst_module)."""
        return self._module_edge_counts

    def get_module_dependencies(self, module: str) -> Dict[str, Dict[str, int]]:
        """Direct outgoing dependencies for a module."""
        deps: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for (src_mod, dst_mod), counts in self.get_module_edge_counts().items():
            if src_mod != module:
                continue
            for edge_type, count in counts.items():
                deps[dst_mod][edge_type] += count
        return deps

    def get_module_dependents(self, module: str) -> Dict[str, Dict[str, int]]:
        """Direct incoming dependents for a module."""
        deps: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for (src_mod, dst_mod), counts in self.get_module_edge_counts().items():
            if dst_mod != module:
                continue
            for edge_type, count in counts.items():
                deps[src_mod][edge_type] += count
        return deps

    def get_modules_in_cycles(self) -> Set[str]:
        """Modules that participate in at least one node-level cycle."""
        modules: Set[str] = set()
        for cycle in self.find_cycles():
            for node_id in cycle:
                modules.add(self._module_from_full_id(node_id))
        return modules

    def to_tree(
        self,
        max_depth: int = 6,
        max_children: int = 20,
        max_roots: int = 8,
        max_lines: int = 800,
    ) -> str:
        """ASCII tree view of the module dependency graph."""
        edge_counts = self.get_module_edge_counts()
        out_adj: Dict[str, List[str]] = defaultdict(list)
        in_degree: Dict[str, int] = defaultdict(int)

        for (src_mod, dst_mod), _counts in edge_counts.items():
            out_adj[src_mod].append(dst_mod)
            in_degree[dst_mod] += 1
            in_degree.setdefault(src_mod, in_degree.get(src_mod, 0))

        # Focus tree view on modules that actually participate in edges.
        active_modules: Set[str] = set()
        for (src_mod, dst_mod) in edge_counts.keys():
            active_modules.add(src_mod)
            active_modules.add(dst_mod)

        modules = sorted(active_modules) if active_modules else sorted(self.get_modules())
        for module in modules:
            in_degree.setdefault(module, 0)

        roots: List[str] = []
        for candidate in (
            "manage.py",
            "main.py",
            "__main__.py",
            "app.py",
            "server.py",
            "index.ts",
            "index.js",
            "main.ts",
            "main.go",
            "main.rs",
        ):
            if candidate in modules:
                roots.append(candidate)
                continue
            matches = [m for m in modules if Path(m).name == candidate]
            if matches:
                # Prefer the shallowest path.
                matches.sort(key=lambda m: (len(Path(m).parts), m))
                roots.append(matches[0])
        if not roots:
            roots = [m for m in modules if in_degree.get(m, 0) == 0]
        if not roots:
            roots = modules[:1] if modules else []
        roots = roots[:max_roots]

        for src in out_adj:
            out_adj[src] = sorted(set(out_adj[src]))

        lines: List[str] = []
        seen: Set[str] = set()

        def _walk(node: str, prefix: str, depth: int) -> None:
            if len(lines) >= max_lines:
                return
            if depth > max_depth:
                lines.append(f"{prefix}`- ...")
                return

            children = out_adj.get(node, [])
            if len(children) > max_children:
                children = children[:max_children] + ["..."]

            for idx, child in enumerate(children):
                if len(lines) >= max_lines:
                    return
                is_last = idx == len(children) - 1
                branch = "`- " if is_last else "|- "
                next_prefix = prefix + ("   " if is_last else "|  ")

                if child == "...":
                    lines.append(f"{prefix}{branch}...")
                    continue

                if child in seen:
                    lines.append(f"{prefix}{branch}{child} (ref)")
                    continue

                lines.append(f"{prefix}{branch}{child}")
                seen.add(child)
                _walk(child, next_prefix, depth + 1)

        for idx, root in enumerate(roots):
            if len(lines) >= max_lines:
                break
            if idx > 0:
                lines.append("")
            lines.append(root)
            seen.add(root)
            _walk(root, "", 1)

        if len(lines) >= max_lines:
            lines.append("")
            lines.append("...(truncated)...")

        return "\n".join(lines) + ("\n" if lines else "")

    def get_summary(self) -> str:
        """Get a human-readable summary of the graph."""
        cycles = self.find_cycles()
        summary = []
        summary.append(f"📊 Multi-Language Dependency Graph Summary")
        summary.append(f"  Total nodes: {len(self.nodes)}")
        summary.append(f"  Total edges (dependencies): {len(self.edges)}")
        summary.append(f"  Circular dependencies found: {len(cycles)}")
        
        if self.languages_found:
            summary.append(f"\n🔍 Languages analyzed:")
            for lang in sorted(self.languages_found):
                summary.append(f"   • {lang}")

        if cycles:
            summary.append(f"\n⚠️  Circular Dependencies Detected:")
            for i, cycle in enumerate(cycles, 1):
                cycle_str = " → ".join([node.split("::")[-1] for node in cycle])
                summary.append(f"  {i}. {cycle_str}")

        return "\n".join(summary)
