import asyncio
import warnings
import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.rule import Rule
from rich.text import Text
from rich.theme import Theme

from .chat_engine import ChatEngine
from .utils import ensure_api_key, pick_session

warnings.filterwarnings(
    "ignore",
    message=r".*Pydantic serializer warnings.*",
)

# ── Theme ──────────────────────────────────────────────────────────────────────

THEME = Theme(
    {
        "primary":   "bold #00d7af",
        "secondary": "#5f87af",
        "accent":    "#ff8700",
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


# ── Main loop ──────────────────────────────────────────────────────────────────

async def chat_loop(thread_id: str):
    engine = ChatEngine()

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
            async for event in engine.stream_turn(user_input, thread_id):
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
                    if chunk and chunk.content:
                        if not hasattr(chat_loop, 'response_started') or not chat_loop.response_started:
                            console.print()
                            console.print(Text("◆ assistant", style="bold #5f87af"))
                            console.print()
                            chat_loop.response_started = True
                        console.print(chunk.content, end="", highlight=False)

            console.print("\n")
            chat_loop.response_started = False

        except Exception as e:
            console.print(f"\n[error]  ✗ Error:[/error] {e}\n")

        console.print(Rule(style="#1c1c1c", characters="╌"))
        console.print()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Launch the normal terminal chat by default."""
    if ctx.invoked_subcommand is None:
        ensure_api_key()
        thread_id = pick_session(console=console)
        console.print()
        asyncio.run(chat_loop(thread_id))


@app.command()
def chat(
    session: str | None = typer.Option(None, "--session", "-s", help="Resume a specific session"),
) -> None:
    """Start the normal terminal chat view."""
    ensure_api_key()
    thread_id = session or pick_session(console=console)
    console.print()
    asyncio.run(chat_loop(thread_id))


if __name__ == "__main__":
    app()
