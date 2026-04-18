"""
demo.py
-------
Self-contained Textual demo — run with:

    python demo.py

Shows:
  1.  ChatScreen with simulated tool calls, streaming text, and a plan panel
  2.  ApprovalScreen with a syntax-highlighted diff
"""

import asyncio
import sys
import os

# Allow running from the repo root without installing the package
sys.path.insert(0, os.path.dirname(__file__))

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Horizontal
from textual.widgets import Input, Static

from tiaga.ui.theme import TEXTUAL_CSS
from tiaga.ui.widgets import (
    RainbowBorder,
    ToolCallBlock,
    AssistantMessage,
    PlanPanel,
    InputBar,
    FooterBar,
    ApprovalSidebar,
    DiffView,
)


# ── sample data ───────────────────────────────────────────────────────────────

SAMPLE_DIFF = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BMI Calculator</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxyg
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }

        .calculator {
            background: white;
            border-radius: 20px;
            padding: 40px;
            width: 100%;
            max-width: 400px;
"""

PLAN_ITEMS = [
    ("Download stock footage of fit sporty people", "active"),
    ("Add video as background to BMI calculator",   "pending"),
    ("Update styles for overlay effect",             "pending"),
]


# ── ChatScreen demo ───────────────────────────────────────────────────────────

class DemoChatScreen(App):
    CSS = TEXTUAL_CSS

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("a",      "show_approval", "Approval demo"),
        Binding("f1",     "quit", "Quit"),
    ]

    async def on_mount(self) -> None:
        asyncio.create_task(self._run_demo())

    def compose(self) -> ComposeResult:
        yield RainbowBorder(id="rainbow-border")
        with Static(id="header"):
            yield Static("🐸  Toad — Claude Code ~/sandbox/bmi",
                         id="header-title", markup=False)
            yield Static("Default", id="header-mode", markup=False)
        with ScrollableContainer(id="messages-scroll"):
            pass
        yield InputBar(id="input-bar")
        yield FooterBar(id="footer")

    def _scroll(self) -> ScrollableContainer:
        return self.query_one("#messages-scroll", ScrollableContainer)

    async def _run_demo(self) -> None:
        await asyncio.sleep(0.4)
        plan: PlanPanel | None = None
        plan_items = [list(item) for item in PLAN_ITEMS]

        def _refresh_plan() -> None:
            nonlocal plan
            if plan is not None:
                plan.set_items([(label, status) for label, status in plan_items])

        def _complete_step(index: int) -> None:
            if 0 <= index < len(plan_items):
                plan_items[index][1] = "done"
                if index + 1 < len(plan_items) and plan_items[index + 1][1] == "pending":
                    plan_items[index + 1][1] = "active"
                _refresh_plan()

        # ── tool call 1: find ──────────────────────────────────────────────
        tool1 = ToolCallBlock(
            call_id="abc12345",
            tool_kind="shell",
            name="shell",
            arguments={"command": 'find . -type f -name "*.html" -o -name "*.css" -o -name "*.js" | head -20'},
        )
        await self._scroll().mount(tool1)
        await asyncio.sleep(0.8)
        from rich.syntax import Syntax
        tool1.mark_done(
            success=True,
            output_renderables=[
                Syntax("./index.html", "text", theme="monokai"),
            ],
        )
        self._scroll().scroll_end(animate=False)
        await asyncio.sleep(0.5)

        # ── tool call 2: ls -la ────────────────────────────────────────────
        tool2 = ToolCallBlock(
            call_id="def67890",
            tool_kind="shell",
            name="shell",
            arguments={"command": "ls -la"},
        )
        await self._scroll().mount(tool2)
        await asyncio.sleep(0.8)
        from rich.text import Text
        tool2.mark_done(
            success=True,
            output_renderables=[
                Syntax(
                    "total 24\ndrwxr-xr-x@  3 willmcgugan  staff    96 30 Jan 19:21 .\n"
                    "drwxr-xr-x  19 willmcgugan  staff   608 30 Jan 19:19 ..\n"
                    "-rw-r--r--@  1 willmcgugan  staff  9762 30 Jan 19:21 index.html",
                    "text",
                    theme="monokai",
                ),
            ],
        )
        self._scroll().scroll_end(animate=False)
        await asyncio.sleep(0.4)

        # ── assistant prose ────────────────────────────────────────────────
        msg = AssistantMessage()
        await self._scroll().mount(msg)
        prose = "Let me read the current HTML file to understand the structure."
        for ch in prose:
            msg.append(ch)
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.3)

        # ── tool call 3: read file ─────────────────────────────────────────
        tool3 = ToolCallBlock(
            call_id="ghi11223",
            tool_kind="read",
            name="read_file",
            arguments={"path": "/Users/willmcgugan/sandbox/bmi/index.html"},
        )
        await self._scroll().mount(tool3)
        await asyncio.sleep(0.9)
        tool3.mark_done(success=True, output_renderables=[
            Text("index.html  ⦁  lines 1-80 of 220", style="#6c7086"),
        ])
        self._scroll().scroll_end(animate=False)
        await asyncio.sleep(0.4)

        # ── second assistant prose ────────────────────────────────────────
        msg2 = AssistantMessage()
        await self._scroll().mount(msg2)
        second = (
            "Now I'll download some stock footage of fit sporty people and add it "
            "as a background video. Let me create a todo list for this task and then proceed. "
            "Now let me download stock footage. I'll use a free stock"
        )
        for ch in second:
            msg2.append(ch)
            await asyncio.sleep(0.018)
        await asyncio.sleep(0.3)

        # ── plan panel ────────────────────────────────────────────────────
        plan = PlanPanel(items=[(label, status) for label, status in plan_items])
        await self._scroll().mount(plan)
        self._scroll().scroll_end(animate=False)
        await asyncio.sleep(0.6)

        # ── plan tracker progress demo ────────────────────────────────────
        tool4 = ToolCallBlock(
            call_id="jkl33445",
            tool_kind="shell",
            name="shell",
            arguments={"command": "download video clip"},
        )
        await self._scroll().mount(tool4)
        await asyncio.sleep(0.8)
        tool4.mark_done(success=True, output_renderables=[Text("Downloaded stock footage.", style="#a6e3a1")])
        _complete_step(0)
        self._scroll().scroll_end(animate=False)
        await asyncio.sleep(0.5)

        tool5 = ToolCallBlock(
            call_id="mno55667",
            tool_kind="write",
            name="edit_file",
            arguments={"path": "./index.html"},
        )
        await self._scroll().mount(tool5)
        await asyncio.sleep(0.8)
        tool5.mark_done(success=True, output_renderables=[Text("Inserted <video> background block.", style="#a6e3a1")])
        _complete_step(1)
        self._scroll().scroll_end(animate=False)
        await asyncio.sleep(0.5)

        tool6 = ToolCallBlock(
            call_id="pqr77889",
            tool_kind="write",
            name="edit_file",
            arguments={"path": "./styles.css"},
        )
        await self._scroll().mount(tool6)
        await asyncio.sleep(0.8)
        tool6.mark_done(success=True, output_renderables=[Text("Updated overlay and contrast styles.", style="#a6e3a1")])
        _complete_step(2)
        self._scroll().scroll_end(animate=False)
        await asyncio.sleep(0.3)

        # ── hint ──────────────────────────────────────────────────────────
        hint = Static(
            "\n  [#6c7086]Press [bold #89b4fa]a[/] to open the Approval diff screen   "
            "[bold #89b4fa]ctrl+c[/] to quit[/]",
            markup=True,
        )
        await self._scroll().mount(hint)
        self._scroll().scroll_end(animate=False)

    def action_quit(self) -> None:
        self.exit()

    def action_show_approval(self) -> None:
        self.push_screen(DemoApprovalScreen())


# ── ApprovalScreen demo ───────────────────────────────────────────────────────

class DemoApprovalScreen(App):
    CSS = TEXTUAL_CSS

    BINDINGS = [
        Binding("ctrl+c,escape,q", "quit", "Back"),
        Binding("up,k",   "move_up",   show=False),
        Binding("down,j", "move_down", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield RainbowBorder(id="rainbow-border")
        with Static(id="header"):
            yield Static(
                "  Auto diff  ▼   [bold]Approval request[/] The Agent wishes to make the following changes",
                id="header-title",
                markup=True,
            )
        with Horizontal(id="approval-screen"):
            yield ApprovalSidebar(
                filenames=["index.html"],
                id="approval-sidebar",
            )
            yield DiffView(
                filename="/Users/willmcgugan/sandbox/bmi/index.html",
                content=SAMPLE_DIFF,
                added=1,
                removed=0,
                language="html",
                id="diff-view",
            )
        footer = Static(
            "  [bold #89b4fa]↑↓[/] Cursor  "
            "[bold #89b4fa]aA[/] Allow once/always  "
            "[bold #89b4fa]r[/] Reject once  "
            "[bold #89b4fa]tab shift+tab[/] Focus  "
            "[bold #89b4fa]jk[/] Navigation  "
            "[bold #89b4fa]f1[/] Help  "
            "[bold #89b4fa]^p[/] palette",
            id="footer",
            markup=True,
        )
        footer.styles.background = "#181825"
        footer.styles.height = 1
        footer.styles.padding = (0, 1)
        yield footer

    def action_quit(self) -> None:
        self.exit()

    def action_move_up(self) -> None:
        try:
            self.query_one("#approval-sidebar", ApprovalSidebar).select_prev()
        except Exception:
            pass

    def action_move_down(self) -> None:
        try:
            self.query_one("#approval-sidebar", ApprovalSidebar).select_next()
        except Exception:
            pass


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "approval":
        DemoApprovalScreen().run()
    else:
        DemoChatScreen().run()
