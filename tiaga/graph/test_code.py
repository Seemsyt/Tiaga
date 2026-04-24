
@click.command()
@click.argument("directory", required=False, default=".")
@click.option("--format", "-f", type=click.Choice(["json", "dot", "summary", "md", "tree"]), default="summary", help="Output format")
@click.option("--output", "-o", type=click.Path(), help="Output file (defaults to ./project_graph/project_graph.<ext>)")
@click.option("--show-cycles", is_flag=True, help="Highlight and show circular dependencies")
@click.option("--module", "-m", help="Analyze specific module/directory")
@click.option("--max-depth", type=int, default=6, show_default=True, help="Tree only: max recursion depth")
@click.option("--max-children", type=int, default=20, show_default=True, help="Tree only: max children per node")
@click.option("--max-roots", type=int, default=8, show_default=True, help="Tree only: max roots to print")
@click.option("--max-lines", type=int, default=800, show_default=True, help="Tree only: max output lines")
@click.option("--cwd", "-c", type=click.Path(exists=True, file_okay=False, path_type=Path), help="Base working directory (also used for default output path)")
def graph_cli(
    directory: str,
    format: str,
    output: str | None,
    show_cycles: bool,
    module: str | None,
    max_depth: int,
    max_children: int,
    max_roots: int,
    max_lines: int,
    cwd: Path | None,
):
    """Analyze codebase and generate multi-language dependency graphs.
    
    Supports: Python, JavaScript, TypeScript, Java, Go, Rust, C, C++

    Examples:
        tiaga-graph                           # Save to ./project_graph/project_graph.summary
        tiaga-graph --format json             # Save to ./project_graph/project_graph.json
        tiaga-graph --format dot              # Save to ./project_graph/project_graph.dot
        tiaga-graph --format md               # Save to ./project_graph/project_graph.md (Mermaid diagram)
        tiaga-graph --format tree             # Save to ./project_graph/project_graph.tree (ASCII)
        tiaga-graph -c /path/to/project       # Use a different base dir for resolving paths/output
        tiaga-graph --show-cycles             # Include circular dependencies analysis
        tiaga-graph --module tiaga.core       # Analyze specific module
        tiaga-graph --output graph.json       # Custom output path
    """
    try:
        output_path, size_bytes = run_graph(
            directory=directory,
            format=format,
            output=output,
            show_cycles=show_cycles,
            module=module,
            tree_max_depth=max_depth,
            tree_max_children=max_children,
            tree_max_roots=max_roots,
            tree_max_lines=max_lines,
            cwd=cwd,
        )
        click.echo(f"graph saved: {output_path.resolve()}")
        click.echo(f"size: {size_bytes} bytes")

    except Exception as e:
        click.echo(f"error analyzing codebase: {e}", err=True)
        if os.getenv("TIAGA_DEBUG"):
            import traceback
            traceback.print_exc()
        raise SystemExit(1)


def run_graph(
    directory: str,
    format: str = "summary",
    output: str | None = None,
    show_cycles: bool = False,
    module: str | None = None,
    tree_max_depth: int = 6,
    tree_max_children: int = 20,
    tree_max_roots: int = 8,
    tree_max_lines: int = 800,
    cwd: Path | None = None,
) -> tuple[Path, int]:
    base_dir = (cwd or Path.cwd()).resolve()

    target_dir = Path(directory)
    if not target_dir.is_absolute():
        target_dir = base_dir / target_dir
    target_dir = target_dir.resolve()
    if not target_dir.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    builder = DependencyGraphBuilder(root_path=str(target_dir))

    if module:
        builder.analyze_directory(module)
    else:
        builder.analyze_directory()

    if show_cycles or format in ("summary", "md"):
        builder.find_cycles()

    if format == "json":
        content = builder.to_json()
        file_ext = "json"
    elif format == "dot":
        content = builder.to_dot()
        file_ext = "dot"
    elif format == "md":
        content = builder.to_markdown()
        file_ext = "md"
    elif format == "tree":
        content = builder.to_tree(
            max_depth=tree_max_depth,
            max_children=tree_max_children,
            max_roots=tree_max_roots,
            max_lines=tree_max_lines,
        )
        file_ext = "tree"
    elif format == "summary":
        content = builder.get_summary()
        file_ext = "summary"
    else:
        raise ValueError(f"Unsupported format: {format}")

    out_dir = _project_graph_dir(base_dir)
    if output:
        output_path = Path(output)
        if not output_path.is_absolute():
            output_path = out_dir / output_path
    else:
        output_path = out_dir / f"project_graph.{file_ext}"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path, len(content)


def _get_base_dir(cwd: Path | None) -> Path:
    try:
        config = load_config(cwd, require_api=False)
        return config.cwd.resolve()
    except Exception:
        return (cwd or Path.cwd()).resolve()


def _project_graph_dir(base_dir: Path) -> Path:
    path = base_dir / "project_graph"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_output_stem(text: str, limit: int = 120) -> str:
    cleaned = []
    for ch in text.strip():
        if ch.isalnum() or ch in ("-", "_", "."):
            cleaned.append(ch)
        elif ch in ("/", "\\", " "):
            cleaned.append("_")
        else:
            cleaned.append("_")
    out = "".join(cleaned).strip("._-") or "item"
    if len(out) > limit:
        out = out[:limit].rstrip("._-")
    return out


def _resolve_target_dir(base_dir: Path, directory: str) -> Path:
    target_dir = Path(directory)
    if not target_dir.is_absolute():
        target_dir = base_dir / target_dir
    return target_dir.resolve()


def _read_role_hint(file_path: Path) -> str | None:
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    lines = text.splitlines()[:80]
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        return None

    first = lines[i].lstrip()
    if first.startswith('"""') or first.startswith("'''"):
        quote = first[:3]
        content = []
        rest = first[3:]
        if rest.endswith(quote) and len(rest) > 0:
            inner = rest[:-3].strip()
            return inner.splitlines()[0].strip() if inner else None
        if rest.strip():
            content.append(rest)
        i += 1
        while i < len(lines):
            if quote in lines[i]:
                before = lines[i].split(quote, 1)[0]
                if before.strip():
                    content.append(before)
                break
            content.append(lines[i])
            i += 1
        hint = "\n".join(content).strip()
        return hint.splitlines()[0].strip() if hint else None

    if first.startswith("#"):
        content = []
        while i < len(lines) and lines[i].lstrip().startswith("#"):
            content.append(lines[i].lstrip()[1:].strip())
            i += 1
        hint = " ".join([c for c in content if c]).strip()
        return hint if hint else None

    if first.startswith("//"):
        content = []
        while i < len(lines) and lines[i].lstrip().startswith("//"):
            content.append(lines[i].lstrip()[2:].strip())
            i += 1
        hint = " ".join([c for c in content if c]).strip()
        return hint if hint else None

    return None


def _format_edges(edge_map: dict[str, dict[str, int]], limit: int = 10) -> list[str]:
    items: list[tuple[str, int]] = []
    for module, counts in edge_map.items():
        items.append((module, sum(counts.values())))
    items.sort(key=lambda x: (-x[1], x[0]))
    return [name for name, _ in items[:limit]]


def _format_edge_counts(counts: dict[str, int]) -> str:
    parts = []
    for edge_type in sorted(counts.keys()):
        parts.append(f"{edge_type}:{counts[edge_type]}")
    return ", ".join(parts)


def _compute_risk_level(score: int) -> str:
    if score >= 5:
        return "HIGH"
    if score >= 3:
        return "MEDIUM"
    return "LOW"


def _impact_suggestion(risk_level: str, in_cycle: bool, fan_in: int, fan_out: int) -> str:
    if in_cycle:
        return "Break cycles by introducing an interface or moving shared types into a separate module."
    if risk_level == "HIGH" and fan_in >= 3:
        return "Stabilize the public surface (types/functions) and add tests; consider an abstraction layer to reduce coupling."
    if risk_level == "HIGH" and fan_out >= 5:
        return "Reduce dependencies by splitting responsibilities or introducing a façade module."
    if risk_level == "MEDIUM":
        return "Make changes incrementally and keep interfaces backward-compatible."
    return "Low blast radius; keep interfaces stable and add/adjust unit tests."


def _module_impact(builder: DependencyGraphBuilder, module: str) -> tuple[list[str], list[str]]:
    # Reverse graph traversal (module-level).
    edge_counts = builder.get_module_edge_counts()
    reverse_adj: dict[str, set[str]] = defaultdict(set)
    for (src_mod, dst_mod), _counts in edge_counts.items():
        reverse_adj[dst_mod].add(src_mod)

    direct = sorted(reverse_adj.get(module, set()))
    indirect: set[str] = set()
    queue = deque(direct)
    seen: set[str] = set([module]) | set(direct)

    while queue:
        cur = queue.popleft()
        for parent in reverse_adj.get(cur, set()):
            if parent in seen:
                continue
            seen.add(parent)
            indirect.add(parent)
            queue.append(parent)

    indirect_list = sorted(indirect)
    # Don't duplicate direct items in indirect section.
    indirect_list = [m for m in indirect_list if m not in direct]
    return direct, indirect_list


@click.group(
    invoke_without_command=True,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.option("--cwd", "-c", type=click.Path(exists=True, file_okay=False, path_type=Path), help="current working dir")
@click.pass_context
def main(ctx: click.Context, cwd: Path | None = None):
    """Tiaga CLI - AI assistant with multi-language codebase analysis.

    Run interactively or with a single prompt.
    """
    print("DEBUG : main trigrrer")
    if ctx.invoked_subcommand:
        return
    prompt = " ".join(ctx.args).strip() if getattr(ctx, "args", None) else None
    if not prompt:
        prompt = None
    try:
        config = load_config(cwd, require_api=bool(prompt))
    except ConfigError as e:
        click.echo(f"config error: {e}", err=True)
        raise SystemExit(1)
    except Exception as e:
        click.echo(f"unexpected startup error: {e}", err=True)
        raise SystemExit(1)
    
    cli_instance = CLI(config)

    if prompt:
        result = asyncio.run(cli_instance.run_single(prompt))
        if result is None:
            raise SystemExit(1)
    else:
        asyncio.run(cli_instance.run_interactive())


@main.command("graph")
@click.argument("directory", required=False, default=".")
@click.option("--format", "-f", type=click.Choice(["tree", "md", "summary", "dot", "json"]), default="tree", help="Output format")
@click.option("--output", "-o", type=click.Path(), help="Write output to file (defaults to ./project_graph/project_graph.<ext>)")
@click.option("--show-cycles", is_flag=True, help="Highlight and show circular dependencies")
@click.option("--module", "-m", help="Analyze specific module/directory")
@click.option("--max-depth", type=int, default=6, show_default=True, help="Tree only: max recursion depth")
@click.option("--max-children", type=int, default=20, show_default=True, help="Tree only: max children per node")
@click.option("--max-roots", type=int, default=8, show_default=True, help="Tree only: max roots to print")
@click.option("--max-lines", type=int, default=800, show_default=True, help="Tree only: max output lines")
@click.option("--cwd", "-c", type=click.Path(exists=True, file_okay=False, path_type=Path), help="Base working directory (defaults to config cwd if available)")
def graph_cmd(
    directory: str,
    format: str,
    output: str | None,
    show_cycles: bool,
    module: str | None,
    max_depth: int,
    max_children: int,
    max_roots: int,
    max_lines: int,
    cwd: Path | None,
):
    base_dir = _get_base_dir(cwd)
    output_path, _size_bytes = run_graph(
        directory=directory,
        format=format,
        output=output,
        show_cycles=show_cycles,
        module=module,
        tree_max_depth=max_depth,
        tree_max_children=max_children,
        tree_max_roots=max_roots,
        tree_max_lines=max_lines,
        cwd=base_dir,
    )
    click.echo(str(output_path))


@main.command("explain")
@click.argument("file")
@click.option("--dir", "-d", "directory", default=".", help="Project directory to analyze (relative to working dir)")
@click.option("--cwd", "-c", type=click.Path(exists=True, file_okay=False, path_type=Path), help="Base working directory (defaults to config cwd if available)")
def explain_cmd(file: str, directory: str, cwd: Path | None):
    base_dir = _get_base_dir(cwd)
    target_dir = _resolve_target_dir(base_dir, directory)
    builder = DependencyGraphBuilder(root_path=str(target_dir))
    builder.analyze_directory()
    builder.find_cycles()

    file_path = Path(file)
    if not file_path.is_absolute():
        file_path = base_dir / file_path
    file_path = file_path.resolve()
    if not file_path.exists():
        raise SystemExit(f"File not found: {file}")
    try:
        module = str(file_path.relative_to(target_dir))
    except ValueError:
        raise SystemExit(f"File must be under analyzed dir: {target_dir}")

    depends_on = builder.get_module_dependencies(module)
    used_by = builder.get_module_dependents(module)
    in_cycle = module in builder.get_modules_in_cycles()

    depends_list = _format_edges(depends_on)
    used_by_list = _format_edges(used_by)

    risks: list[str] = []
    if in_cycle:
        risks.append("Circular dependency involvement")
    for dep in depends_list:
        if module in builder.get_module_dependencies(dep):
            risks.append(f"Tight coupling with {dep}")
            break
    if len(used_by_list) >= 3:
        risks.append("High blast radius (many dependents)")

    role_hint = _read_role_hint(file_path) or "No module description found."

    lines: list[str] = []
    lines.append(f"📄 {module}")
    lines.append("")
    lines.append("Role:")
    lines.append(role_hint)
    lines.append("")
    lines.append("Depends on:")
    if depends_list:
        for dep in depends_list[:10]:
            lines.append(f"→ {dep} ({_format_edge_counts(depends_on.get(dep, {}))})")
    else:
        lines.append("→ (none)")
    lines.append("")
    lines.append("Used by:")
    if used_by_list:
        for dep in used_by_list[:10]:
            lines.append(f"→ {dep} ({_format_edge_counts(used_by.get(dep, {}))})")
    else:
        lines.append("→ (none)")
    lines.append("")
    lines.append("Risk:")
    if risks:
        for risk in risks:
            lines.append(f"⚠ {risk}")
    else:
        lines.append("✓ Low coupling")
    lines.append("")
    lines.append("Summary:")
    lines.append(f"Direct deps: {len(depends_on)} | Direct dependents: {len(used_by)} | Cycles: {'yes' if in_cycle else 'no'}")
    lines.append("")

    out_dir = _project_graph_dir(base_dir)
    out_path = out_dir / f"explain_{_safe_output_stem(module)}.txt"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    click.echo(str(out_path))


@main.command("impact")
@click.argument("file")
@click.option("--dir", "-d", "directory", default=".", help="Project directory to analyze (relative to working dir)")
@click.option("--cwd", "-c", type=click.Path(exists=True, file_okay=False, path_type=Path), help="Base working directory (defaults to config cwd if available)")
def impact_cmd(file: str, directory: str, cwd: Path | None):
    base_dir = _get_base_dir(cwd)
    target_dir = _resolve_target_dir(base_dir, directory)
    builder = DependencyGraphBuilder(root_path=str(target_dir))
    builder.analyze_directory()
    builder.find_cycles()

    file_path = Path(file)
    if not file_path.is_absolute():
        file_path = base_dir / file_path
    file_path = file_path.resolve()
    if not file_path.exists():
        raise SystemExit(f"File not found: {file}")
    try:
        module = str(file_path.relative_to(target_dir))
    except ValueError:
        raise SystemExit(f"File must be under analyzed dir: {target_dir}")

    direct, indirect = _module_impact(builder, module)
    depends_on = builder.get_module_dependencies(module)
    in_cycle = module in builder.get_modules_in_cycles()

    score = 0
    if in_cycle:
        score += 3
    if len(direct) >= 5:
        score += 3
    elif len(direct) >= 2:
        score += 2
    if len(depends_on) >= 6:
        score += 2
    elif len(depends_on) >= 3:
        score += 1
    risk_level = _compute_risk_level(score)

    lines: list[str] = []
    lines.append(f"📊 Impact Report: {module}")
    lines.append("")
    lines.append("Affected Files:")
    if direct:
        for item in direct[:20]:
            lines.append(f"→ {item}")
    else:
        lines.append("→ (none)")
    lines.append("")
    lines.append("Indirect Impact:")
    if indirect:
        for item in indirect[:20]:
            lines.append(f"→ {item}")
    else:
        lines.append("→ (none)")
    lines.append("")
    lines.append(f"Risk Level: {risk_level}")
    lines.append("")
    lines.append("Suggestion:")
    lines.append(_impact_suggestion(risk_level, in_cycle=in_cycle, fan_in=len(direct), fan_out=len(depends_on)))
    lines.append("")

    out_dir = _project_graph_dir(base_dir)
    out_path = out_dir / f"impact_{_safe_output_stem(module)}.txt"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    click.echo(str(out_path))
