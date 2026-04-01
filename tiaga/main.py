import asyncio
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

import aiosqlite
import typer
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from graph import graph

# ── Theme ──────────────────────────────────────────────────────────────────────

THEME = Theme(
    {
        "primary":   "bold #00d7af",   # teal
        "secondary": "#5f87af",        # steel blue
        "accent":    "#ff8700",        # amber
        "muted":     "dim #767676",
        "success":   "#00af5f",
        "error":     "bold #ff5f5f",
        "user_tag":  "bold #00d7af",
        "ai_tag":    "bold #5f87af",
        "tool_tag":  "italic #767676",
        "border":    "#1c1c1c",
    }
)

console = Console(theme=THEME, highlight=False)
app = typer.Typer(add_completion=False)

DB_PATH = str(Path.home() / ".tiaga" / "chat_history.db")
os.makedirs(Path.home() / ".tiaga", exist_ok=True)

SLUG_RE = re.compile(r"[^\w\-]")  # only word chars and hyphens in session names

# ── Helpers ────────────────────────────────────────────────────────────────────

def _slug(name: str) -> str:
    """Normalise a session name: lowercase, spaces→hyphens, strip specials."""
    name = name.strip().lower()
    name = re.sub(r"\s+", "-", name)
    name = SLUG_RE.sub("", name)
    return name[:48]  # max length


def _auto_name() -> str:
    """Generate a timestamped fallback name."""
    return datetime.now().strftime("session-%Y%m%d-%H%M%S")


def ensure_api_key() -> None:
    load_dotenv()
    api_key = os.getenv("OPEN_ROUTER_API_KEY", "").strip()
    if api_key:
        return

    console.print()
    console.print(Panel(
        "[primary]OpenRouter API key not found.[/primary]\n"
        "[muted]Get one at [link=https://openrouter.ai]openrouter.ai[/link][/muted]",
        border_style="#5f87af",
        padding=(1, 3),
    ))
    api_key = Prompt.ask("[primary]  API key[/primary]").strip()
    if not api_key:
        console.print("[error]API key is required.[/error]")
        raise typer.Exit(1)

    env_path = Path(".env")
    if env_path.exists():
        lines = env_path.read_text().splitlines()
        new_lines, key_set = [], False
        for line in lines:
            if line.strip().startswith("OPEN_ROUTER_API_KEY="):
                new_lines.append(f'OPEN_ROUTER_API_KEY="{api_key}"')
                key_set = True
            else:
                new_lines.append(line)
        if not key_set:
            new_lines.append(f'OPEN_ROUTER_API_KEY="{api_key}"')
        env_path.write_text("\n".join(new_lines) + "\n")
    else:
        env_path.write_text(f'OPEN_ROUTER_API_KEY="{api_key}"\n')

    os.environ["OPEN_ROUTER_API_KEY"] = api_key
    console.print("[success]  ✓ Key saved to .env[/success]\n")


# ── Session picker ─────────────────────────────────────────────────────────────

async def list_threads(db_path: str) -> list[str]:
    try:
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute(
                "SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id"
            )
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
    except Exception:
        return []


def pick_session() -> str:
    threads = asyncio.run(list_threads(DB_PATH))

    # ── Header ─────────────────────────────────────────────────────────────────
    console.print()
    console.print(Align.center(
        Text("◈  TIAGA", style="primary bold", justify="center")
    ))
    console.print(Align.center(
        Text("AI terminal assistant", style="muted", justify="center")
    ))
    console.print()

    if threads:
        table = Table(
            box=box.MINIMAL,
            show_header=True,
            header_style="bold #5f87af",      # secondary bold — literal value
            border_style="#1c1c1c",           # border
            padding=(0, 2),
            show_edge=False,
        )
        table.add_column("  #", style="dim #767676", width=4, justify="right")
        table.add_column("Session", style="bold")
        table.add_column("", style="dim #767676")  # hint column

        for i, t in enumerate(threads, 1):
            hint = "[dim]resume[/dim]" if i == 1 else ""
            table.add_row(str(i), t, hint)

        console.print(Panel(
            table,
            title="[#5f87af]Past Sessions[/#5f87af]",
            border_style="#5f87af",
            padding=(0, 1),
        ))
        console.print(
            "[muted]  Enter a [bold]number[/bold] to resume, "
            "or type a [bold]name[/bold] to start a new session "
            "(blank = auto-name).[/muted]\n"
        )
    else:
        console.print(
            Panel(
                "[muted]No past sessions yet.\n"
                "Type a session name or press Enter for an auto-generated one.[/muted]",
                border_style="#1c1c1c",
                padding=(0, 2),
            )
        )
        console.print()

    while True:
        raw = Prompt.ask("[primary]  Session[/primary]", default="").strip()

        # Blank → auto-name
        if not raw:
            chosen = _auto_name()
            console.print(f"[muted]  ↳ Auto-named: [bold]{chosen}[/bold][/muted]")
            return chosen

        # Numeric → resume existing
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(threads):
                chosen = threads[idx]
                console.print(f"[muted]  ↳ Resuming: [bold]{chosen}[/bold][/muted]")
                return chosen
            console.print(
                f"[error]  No session #{raw}. "
                f"Pick 1–{len(threads)} or type a name.[/error]"
            )
            continue

        # Named → slugify and accept
        chosen = _slug(raw)
        if not chosen:
            console.print("[error]  Name must contain at least one letter or digit.[/error]")
            continue

        if chosen != raw:
            console.print(f"[muted]  ↳ Saved as: [bold]{chosen}[/bold][/muted]")
        return chosen


# ── Chat turn ──────────────────────────────────────────────────────────────────

async def run_turn(user_input: str, thread_id: str, compiled_workflow) -> None:
    config = {"configurable": {"thread_id": thread_id}}
    input_ = {"messages": [HumanMessage(content=user_input)]}

    tool_lines: list[str] = []
    current_run_id = None
    response_started = False
    got_first_token = False

    events = compiled_workflow.astream_events(input=input_, config=config, version="v2")

    # ── Phase 1: spinner until first real content arrives ──────────────────────
    # Peek at events manually so we can drop the spinner the moment
    # the first AI token or tool call shows up.
    spinner = Spinner("dots2", text=Text(" thinking…", style="dim #767676"))
    event_buffer = []

    with Live(spinner, console=console, refresh_per_second=12, transient=True):
        async for event in events:
            event_buffer.append(event)
            kind = event["event"]
            if kind in ("on_tool_start", "on_chat_model_stream"):
                break   # drop spinner, handle everything below

    # ── Phase 2: process buffered + remaining events, print live ───────────────
    async def _all_events():
        for e in event_buffer:
            yield e
        async for e in events:
            yield e

    async for event in _all_events():
        kind = event["event"]

        if kind == "on_tool_start":
            tool_name = event["name"]
            tool_input = event["data"].get("input", {})
            hint = ""
            if isinstance(tool_input, dict):
                first_val = next(iter(tool_input.values()), "")
                hint = f": {str(first_val)[:60]}" if first_val else ""
            console.print(f"\n[dim #767676]  🔧 {tool_name}{hint}[/dim #767676]")

        elif kind == "on_tool_end":
            output = str(event["data"].get("output", ""))
            preview = output.replace("\n", " ")[:120]
            if len(output) > 120:
                preview += "…"
            console.print(f"[dim #767676]     ↳ {preview}[/dim #767676]")

        elif kind == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if not chunk or not chunk.content:
                continue

            run_id = event.get("run_id")
            if run_id != current_run_id:
                current_run_id = run_id
                response_started = False

            if not response_started:
                console.print()
                console.print(Text("◆ assistant", style="bold #5f87af"))
                console.print()
                response_started = True

            # Print each chunk immediately — this is the actual stream
            console.print(chunk.content, end="", highlight=False)

    console.print("\n")


# ── Main loop ──────────────────────────────────────────────────────────────────

async def chat_loop(thread_id: str) -> None:
    async with AsyncSqliteSaver.from_conn_string(DB_PATH) as checkpointer:
        compiled = graph.compile(checkpointer=checkpointer)

        # Session header
        console.print()
        console.print(Rule(
            title=f"[#5f87af] {thread_id} [/#5f87af]",
            style="#1c1c1c",
            characters="─",
        ))
        console.print(
            "[muted]  Type [bold]exit[/bold] · [bold]quit[/bold] · "
            "[bold]Ctrl+C[/bold] to leave[/muted]\n"
        )

        while True:
            try:
                console.print(Text("◇ you", style="user_tag"))
                user_input = Prompt.ask("  ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[muted]  Goodbye.[/muted]")
                break

            if not user_input:
                continue

            if user_input.lower() in {"exit", "quit", "bye"}:
                console.print("[muted]  Goodbye.[/muted]")
                break

            try:
                await run_turn(user_input, thread_id, compiled)
            except Exception as e:
                console.print(f"\n[error]  ✗ Error:[/error] {e}\n")

            console.print(Rule(style="#1c1c1c", characters="╌"))
            console.print()


@app.command()
def chat() -> None:
    """Start the Tiaga AI assistant."""
    ensure_api_key()
    thread_id = pick_session()
    console.print()
    asyncio.run(chat_loop(thread_id))


if __name__ == "__main__":
    app()