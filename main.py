import asyncio
import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich import box
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from graph import graph  # import the uncompiled graph
import aiosqlite

console = Console()
DB_PATH = "chat_history.db"

WELCOME = """[bold cyan]AI Assistant[/bold cyan] [dim]— type [bold]exit[/bold] or [bold]quit[/bold] to leave[/dim]"""


# ── Session helpers ────────────────────────────────────────────────────────────

async def list_threads(db_path: str) -> list[str]:
    """Return distinct thread_ids saved in the checkpoint DB."""
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
    """
    Show existing sessions, let user pick one or create a new one.
    Returns the chosen thread_id string.
    """
    threads = asyncio.run(list_threads(DB_PATH))

    if threads:
        table = Table(
            title="Past Sessions",
            box=box.SIMPLE_HEAVY,
            border_style="cyan",
            show_lines=False,
        )
        table.add_column("#", style="dim", width=4)
        table.add_column("Session name", style="bold")

        for i, t in enumerate(threads, 1):
            table.add_row(str(i), t)

        console.print()
        console.print(table)
        console.print(
            "[dim]Enter a number to resume, or type a new session name to start fresh.[/dim]\n"
        )
    else:
        console.print("\n[dim]No past sessions found. Starting a new one.[/dim]\n")

    raw = Prompt.ask("[bold cyan]Session[/bold cyan]").strip()

    # If user typed a number, resolve to thread name
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(threads):
            chosen = threads[idx]
            console.print(f"[dim]Resuming → [bold]{chosen}[/bold][/dim]")
            return chosen

    return raw  # new or manually typed name


# ── One chat turn ──────────────────────────────────────────────────────────────

async def run_turn(
    user_input: str,
    thread_id: str,
    compiled_workflow,
) -> None:
    """Stream one turn. Checkpointer handles history automatically."""
    config = {"configurable": {"thread_id": thread_id}}
    input_ = {"messages": [HumanMessage(content=user_input)]}

    tool_used = False
    response_started = False
    current_run_id = None

    async for event in compiled_workflow.astream_events(input=input_, config=config, version="v2"):

        if event["event"] == "on_tool_start":
            if not tool_used:
                console.print()
            console.print(f"  [dim]🔧 {event['name']}...[/dim]")
            tool_used = True

        elif event["event"] == "on_tool_end":
            output = str(event["data"].get("output", ""))
            preview = output[:200].replace("\n", " ")
            if len(output) > 200:
                preview += "…"
            console.print(f"  [dim]   ↳ {preview}[/dim]")

        elif event["event"] == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if not chunk or not chunk.content:
                continue

            run_id = event.get("run_id")
            if run_id != current_run_id:
                if response_started:
                    console.print()
                console.print("\n[bold green]assistant[/bold green]  ", end="")
                current_run_id = run_id
                response_started = True

            console.print(chunk.content, end="", highlight=False)

    console.print()


# ── Main loop ──────────────────────────────────────────────────────────────────

async def chat_loop(thread_id: str) -> None:
    async with AsyncSqliteSaver.from_conn_string(DB_PATH) as checkpointer:
        compiled = graph.compile(checkpointer=checkpointer)

        console.print(Panel(WELCOME, border_style="cyan", padding=(0, 2)))
        console.print(f"[dim]Session: [bold]{thread_id}[/bold][/dim]")

        while True:
            try:
                console.print()
                user_input = Prompt.ask("[bold cyan]you[/bold cyan]").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Bye![/dim]")
                break

            if not user_input:
                continue

            if user_input.lower() in {"exit", "quit", "bye"}:
                console.print("[dim]Bye![/dim]")
                break

            try:
                await run_turn(user_input, thread_id, compiled)
            except Exception as e:
                console.print(f"\n[red]Error:[/red] {e}")

            console.print(Rule(style="dim"))


def main() -> None:
    thread_id = pick_session()
    asyncio.run(chat_loop(thread_id))


if __name__ == "__main__":
    typer.run(main)