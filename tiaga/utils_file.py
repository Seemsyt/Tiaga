"""
Shared utilities for Tiaga.
"""

import asyncio
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = os.getenv("TIAGA_DB_PATH", str(Path.home() / ".tiaga" / "chat_history.db"))
os.makedirs(Path(DB_PATH).parent, exist_ok=True)

SLUG_RE = re.compile(r"[^\w\-]")


def _slug(name: str) -> str:
    """Normalise a session name."""
    name = name.strip().lower()
    name = re.sub(r"\s+", "-", name)
    name = SLUG_RE.sub("", name)
    return name[:48]


def _auto_name() -> str:
    """Generate a timestamped fallback name."""
    return datetime.now().strftime("session-%Y%m%d-%H%M%S")


async def list_threads(db_path: str) -> list[str]:
    """List all session thread IDs from database."""
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id"
            ).fetchall()
        return [row[0] for row in rows]
    except Exception:
        return []


def ensure_api_key(console=None) -> str:
    """Ensure API key is available, prompt if needed."""
    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.getenv("OPEN_ROUTER_API_KEY", "").strip()
    if api_key:
        return api_key

    # If no console provided, use simple print
    if console is None:
        print("OpenRouter API key not found.")
        print("Get one at https://openrouter.ai")
        api_key = input("Enter your API key: ").strip()
    else:
        from rich.console import Console
        from rich.panel import Panel
        from rich.prompt import Prompt
        from rich.theme import Theme

        THEME = Theme(
            {
                "primary": "bold #00d7af",
                "muted": "dim #767676",
                "error": "bold #ff5f5f",
            }
        )
        console = Console(theme=THEME, highlight=False)

        console.print()
        console.print(Panel(
            "[primary]OpenRouter API key not found.[/primary]\n"
            "[muted]Get one at [link=https://openrouter.ai]openrouter.ai[/link][/muted]",
            border_style="#5f87af",
            padding=(1, 3),
        ))
        api_key = Prompt.ask("[primary]  API key[/primary]").strip()

    if not api_key:
        if console:
            console.print("[error]API key is required.[/error]")
        raise SystemExit(1)

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
    if console:
        console.print("[success]  ✓ Key saved to .env[/success]\n")
    return api_key


def pick_session(console=None, db_path: str = DB_PATH) -> str:
    """Prompt for a session name or allow resuming an existing one."""
    from rich import box
    from rich.align import Align
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.table import Table
    from rich.text import Text
    from rich.theme import Theme

    if console is None:
        theme = Theme(
            {
                "primary": "bold #00d7af",
                "muted": "dim #767676",
                "error": "bold #ff5f5f",
            }
        )
        console = Console(theme=theme, highlight=False)

    threads = asyncio.run(list_threads(db_path))

    console.print()
    console.print(Align.center(Text("◈  TIAGA", style="primary bold", justify="center")))
    console.print(Align.center(Text("AI terminal assistant", style="muted", justify="center")))
    console.print()

    if threads:
        table = Table(
            box=box.MINIMAL,
            show_header=True,
            header_style="bold #5f87af",
            border_style="#1c1c1c",
            padding=(0, 2),
            show_edge=False,
        )
        table.add_column("  #", style="dim #767676", width=4, justify="right")
        table.add_column("Session", style="bold")
        table.add_column("", style="dim #767676")

        for index, thread in enumerate(threads, 1):
            hint = "[dim]resume[/dim]" if index == 1 else ""
            table.add_row(str(index), thread, hint)

        console.print(
            Panel(
                table,
                title="[#5f87af]Past Sessions[/#5f87af]",
                border_style="#5f87af",
                padding=(0, 1),
            )
        )
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

        if not raw:
            chosen = _auto_name()
            console.print(f"[muted]  ↳ Auto-named: [bold]{chosen}[/bold][/muted]")
            return chosen

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

        chosen = _slug(raw)
        if not chosen:
            console.print("[error]  Name must contain at least one letter or digit.[/error]")
            continue

        if chosen != raw:
            console.print(f"[muted]  ↳ Saved as: [bold]{chosen}[/bold][/muted]")
        return chosen
