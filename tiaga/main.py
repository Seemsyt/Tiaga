from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Any

import click
import asyncio

from tiaga.agent.persistence import PersistenceManager, SessionSnapshot
from tiaga.agent.session import Session
from tiaga.config.config import ApprovalPolicy, Config
from tiaga.config.loader import load_config, update_config
from tiaga.utils.errors import ConfigError
from tiaga.tracing.trace import Trace
from tiaga.agent.agent import Agent, AgentEventType
from tiaga.analysis.graph_builder import DependencyGraphBuilder
from tiaga.ui.minimal import ModernUI


# ── Session restore helper ─────────────────────────────────────────────────────

async def _restore_session_from_snapshot(agent: Agent, config: Config, snapshot: SessionSnapshot) -> Session:
    """Build a live Session from a persisted snapshot and swap it into the agent."""
    session = Session(config=config)
    await session.initialize()

    session.created    = snapshot.created_at
    session.session_id = snapshot.session_id
    session.updated    = snapshot.updated_at
    session.turn_count = snapshot.turn_count
    session.context_manager.total_usage = snapshot.total_usage

    for msg in snapshot.messages:
        role = msg.get("role")
        if role == "system":
            continue
        elif role == "user":
            session.context_manager.add_user_message(msg.get("content", ""))
        elif role == "assistant":
            session.context_manager.add_assistant_message(
                msg.get("content", ""), msg.get("tool_calls")
            )
        elif role == "tool":
            session.context_manager.add_tool_message(
                msg.get("tool_call_id", ""), msg.get("content", "")
            )

    await agent.session.mcp_manager.shutdown()
    await agent.session.client.close_client()
    agent.session = session
    return session


# ── CLI ────────────────────────────────────────────────────────────────────────

class CLI:
    def __init__(self, config: Config):
        self.config = config
        self.agent: Agent | None = None
        self.ui = ModernUI(config)
        self.persistence_manager = PersistenceManager()

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _ui_note(self, text: str) -> None:
        self.ui.post_message(text)

    def _build_session_snapshot(self) -> SessionSnapshot | None:
        if not self.agent or not self.agent.session or not self.agent.session.context_manager:
            return None
        return SessionSnapshot(
            session_id=self.agent.session.session_id,
            created_at=self.agent.session.created,
            updated_at=self.agent.session.updated,
            turn_count=self.agent.session.turn_count,
            messages=self.agent.session.context_manager.get_messages(),
            total_usage=self.agent.session.context_manager.total_usage,
            title=getattr(self.agent.session, "title", ""),  # ← carry title through
        )

    def _persist_session(self, announce: bool = False) -> None:
        snapshot = self._build_session_snapshot()
        if snapshot is None:
            return
        try:
            self.persistence_manager.save_session(snapshot)
            if announce:
                self._ui_note(f"session saved: {snapshot.session_id}")
        except Exception as exc:
            click.echo(f"warning: failed to save session: {exc}", err=True)
            if announce:
                self._ui_note(f"failed to save session: {exc}")

    def check_api(self) -> bool:
        return not (
            self.config.api_key_value == "set_api_key"
            or self.config.base_url_value == "set_base_url"
            or self.config.model.name == ""
        )

    # ── Run loops ──────────────────────────────────────────────────────────────

    async def run_interactive(self):
        self.ui.print_welcome()

        async with Agent(self.config, self.ui.handle_confirmation) as agent:
            self.agent = agent

            while True:
                try:
                    user_input = self.ui.prompt_user().strip()
                    if not user_input:
                        continue

                    if user_input.startswith("/"):
                        if not await self.handle_command(user_input):
                            break
                        continue

                    if not self.check_api():
                        self._ui_note("set /base_url, /api_key, and /model before chatting")
                        continue

                    Trace.trace_before_agent(user_message=user_input)
                    response = await self._process_message(user_input)
                    Trace.trace_after_agent(
                        user_message=user_input,
                        final_response=response or "",
                        latency=None,
                        turn_count=self.agent.session.turn_count if self.agent and self.agent.session else None,
                        token_usage=(
                            self.agent.session.context_manager.total_usage
                            if self.agent and self.agent.session and self.agent.session.context_manager
                            else None
                        ),
                    )
                    self._persist_session()

                except KeyboardInterrupt:
                    self._ui_note("use /exit to quit")

        self._persist_session()
        self._ui_note("bye")

    async def run_single(self, message: str):
        async with Agent(self.config, self.ui.handle_confirmation) as agent:
            self.agent = agent
            message = (message or "").strip()
            if not message:
                return ""

            if message.startswith("/"):
                should_continue = await self.handle_command(message)
                return "" if should_continue else None

            if not self.check_api():
                click.echo("set /base_url, /api_key, and /model before chatting", err=True)
                return None

            Trace.trace_before_agent(user_message=message)
            response = await self._process_message(message)
            Trace.trace_after_agent(
                user_message=message,
                final_response=response or "",
                latency=None,
                turn_count=self.agent.session.turn_count if self.agent and self.agent.session else None,
                token_usage=(
                    self.agent.session.context_manager.total_usage
                    if self.agent and self.agent.session and self.agent.session.context_manager
                    else None
                ),
            )
            self._persist_session()
            return response

    async def _process_message(self, message: str):
        if not self.agent or not self.agent.session:
            return None

        self.agent.session.increment_turn()
        final_response: str | None = None

        try:
            async for event in self.agent.run(message):

                if event.type == AgentEventType.TOOL_CALL_START:
                    self.ui.render_tool_call_start(
                        name=event.data.get("name", "unknown"),
                        arguments=event.data.get("arguments", {}),
                    )

                elif event.type == AgentEventType.TOOL_CALL_END:
                    self.ui.render_tool_call_end(
                        name=event.data.get("name", "unknown"),
                        success=bool(event.data.get("success", False)),
                        error=event.data.get("error"),
                    )

                elif event.type == AgentEventType.TEXT_DELTA:
                    content = event.data.get("content", "")
                    self.ui.stream(content)

                elif event.type == AgentEventType.TEXT_COMPLETE:
                    final_response = event.data.get("content", "")
                    self.ui.end_stream()

                elif event.type == AgentEventType.AGENT_ERROR:
                    self._ui_note(f"error: {event.data.get('error', 'unknown error')}")

        except Exception as exc:
            self._ui_note(f"agent crashed: {exc}")

        return final_response

    # ── Commands ───────────────────────────────────────────────────────────────

    async def handle_command(self, command: str) -> bool:
        parts = command.strip().split(maxsplit=1)
        cmd  = parts[0].lower()
        args = parts[1].strip() if len(parts) > 1 else ""

        # ── Navigation ────────────────────────────────────────────────────────

        if cmd in ("/exit", "/quit", "/q"):
            self._persist_session()
            self.ui.shutdown()
            return False

        elif cmd == "/help":
            self._ui_note("\n".join([
                "commands:",
                "  /help",
                "  /exit | /quit | /q",
                "  /clear",
                "  /config",
                "  /stats",
                "  /model   [name]",
                "  /api_key [key]",
                "  /base_url [url]",
                "  /approval [on_request|on_failure|auto|auto_edit|never|yolo]",
                "  /tools",
                "  /mcp",
                "  /save",
                "  /title   <title>",
                "  /sessions",
                "  /resume   <session_id>",
                "  /checkpoint",
                "  /checkpoints <session_id>",
                "  /restore  <checkpoint_id>",
                "  /graph [DIR] [--format json|dot|summary|md|tree]",
                "           [--output FILE] [--show-cycles] [--module PATH]",
            ]))

        # ── Session / history ─────────────────────────────────────────────────

        elif cmd == "/clear":
            if self.agent and self.agent.session:
                self.agent.session.context_manager.clear()
                self._ui_note("conversation cleared")
            else:
                self._ui_note("no active session")

        elif cmd == "/save":
            self._persist_session(announce=True)

        elif cmd == "/title":
            if not args:
                # Show current title
                current = getattr(self.agent.session, "title", "") if self.agent and self.agent.session else ""
                self._ui_note(f"current title: {current!r}" if current else "no title set")
            else:
                if not self.agent or not self.agent.session:
                    self._ui_note("no active session")
                else:
                    self.agent.session.title = args
                    self.persistence_manager.update_session_title(
                        self.agent.session.session_id, args
                    )
                    self._ui_note(f"title set: {args}")

        elif cmd == "/sessions":
            pm = PersistenceManager()
            sessions = pm.list_sessions()
            if not sessions:
                self._ui_note("no saved sessions")
            else:
                self._ui_note("saved sessions")
                for s in sessions:
                    title_part = f"  [{s['title']}]" if s.get("title") else ""
                    self._ui_note(
                        f"  {s['session_id']}{title_part}  "
                        f"updated: {s['updated_at']}  turns: {s['turn_count']}"
                    )

        elif cmd == "/resume":
            if not args:
                self._ui_note("usage: /resume <session_id>")
            else:
                pm = PersistenceManager()
                snapshot = pm.load_session(args)
                if not snapshot:
                    self._ui_note(f"session not found: {args}")
                else:
                    session = await _restore_session_from_snapshot(self.agent, self.config, snapshot)
                    session.title = snapshot.title          # ← restore title onto live session
                    title_part = f"  ({snapshot.title})" if snapshot.title else ""
                    self._ui_note(f"session resumed: {session.session_id}{title_part}")

        elif cmd == "/checkpoint":
            snapshot = self._build_session_snapshot()
            if snapshot is None:
                self._ui_note("no active session to checkpoint")
            else:
                checkpoint_id = self.persistence_manager.save_checkpoint(snapshot)
                self._ui_note(f"checkpoint saved: {checkpoint_id}")

        elif cmd == "/checkpoints":
            if not args:
                self._ui_note("usage: /checkpoints <session_id>")
            else:
                pm = PersistenceManager()
                checkpoints = pm.list_checkpoints(args)
                if not checkpoints:
                    self._ui_note("no checkpoints found")
                else:
                    self._ui_note("checkpoints")
                    for cp in checkpoints:
                        title_part = f"  [{cp['title']}]" if cp.get("title") else ""
                        self._ui_note(
                            f"  {cp['checkpoint_id']}{title_part}  "
                            f"turns: {cp['turn_count']}  saved: {cp['created_at']}"
                        )

        elif cmd == "/restore":
            if not args:
                self._ui_note("usage: /restore <checkpoint_id>")
            else:
                pm = PersistenceManager()
                snapshot = pm.load_checkpoint(args)
                if not snapshot:
                    self._ui_note(f"checkpoint not found: {args}")
                else:
                    session = await _restore_session_from_snapshot(self.agent, self.config, snapshot)
                    session.title = snapshot.title          # ← restore title onto live session
                    self._ui_note(f"session restored from checkpoint: {args}  →  {session.session_id}")

        # ── Config ────────────────────────────────────────────────────────────

        elif cmd == "/config":
            self._ui_note("\n".join([
                "configuration",
                f"  model       {self.config.model_name}",
                f"  temperature {self.config.temperature}",
                f"  approval    {self.config.approval.value}",
                f"  cwd         {self.config.cwd}",
                f"  max turns   {self.config.max_turns}",
                f"  hooks       {self.config.hooks_enabled}",
            ]))

        elif cmd == "/model":
            if args:
                self.config.model.name = args
                update_config({"model": {"name": args}})
                try:
                    self.config = load_config(self.config.cwd, require_api=False)
                    self._ui_note(f"model set: {args}")
                except Exception as exc:
                    self._ui_note(f"failed to reload config: {exc}")
            else:
                self._ui_note(f"current model: {self.config.model_name}")

        elif cmd == "/api_key":
            if args:
                self.config.api_key_value = args
                update_config({"api_key": args})
                try:
                    self.config = load_config(self.config.cwd, require_api=False)
                    self._ui_note("api key updated")
                except Exception as exc:
                    self._ui_note(f"failed to reload config: {exc}")
            else:
                masked = (
                    "*" * len(self.config.api_key_value)
                    if self.config.api_key_value != "set_api_key"
                    else "not set"
                )
                self._ui_note(f"current api key: {masked}")

        elif cmd == "/base_url":
            if args:
                self.config.base_url_value = args
                update_config({"base_url": args})
                try:
                    self.config = load_config(self.config.cwd, require_api=False)
                    self._ui_note(f"base url set: {args}")
                except Exception as exc:
                    self._ui_note(f"failed to reload config: {exc}")
            else:
                self._ui_note(f"current base url: {self.config.base_url_value}")

        elif cmd == "/approval":
            if args:
                try:
                    approval = ApprovalPolicy(args)
                    update_config({"approval": approval.value})
                    try:
                        self.config = load_config(self.config.cwd, require_api=False)
                        self._ui_note(f"approval set: {args}")
                    except Exception as exc:
                        self._ui_note(f"failed to reload config: {exc}")
                except ValueError:
                    self._ui_note(f"invalid approval policy: {args}")
                    self._ui_note(f"valid options: {', '.join(p.value for p in ApprovalPolicy)}")
            else:
                self._ui_note(f"current approval: {self.config.approval.value}")

        # ── Info ──────────────────────────────────────────────────────────────

        elif cmd == "/stats":
            if self.agent and self.agent.session:
                stats = self.agent.session.get_stats()
                lines = ["stats"] + [f"  {k}: {v}" for k, v in stats.items()]
                self._ui_note("\n".join(lines))
            else:
                self._ui_note("no active session")

        elif cmd == "/tools":
            if self.agent and self.agent.session:
                tools = self.agent.session.tool_registry.get_tools()
                lines = [f"available tools ({len(tools)})"] + [f"  {t.name}" for t in tools]
                self._ui_note("\n".join(lines))
            else:
                self._ui_note("no active session")

        elif cmd == "/mcp":
            if self.agent and self.agent.session:
                servers = self.agent.session.tool_registry.mcp_tools
                lines = [f"mcp servers ({len(servers)})"] + [f"  {s.name}" for s in servers]
                self._ui_note("\n".join(lines))
            else:
                self._ui_note("no active session")

        # ── Graph ─────────────────────────────────────────────────────────────

        elif cmd == "/graph":
            directory   = "."
            fmt         = "summary"
            output: str | None = None
            show_cycles = False
            module: str | None = None

            try:
                tokens = shlex.split(args)
            except ValueError as exc:
                self._ui_note(f"invalid arguments: {exc}")
                return True

            i = 0
            while i < len(tokens):
                tok = tokens[i]
                if tok in ("--format", "-f"):
                    if i + 1 >= len(tokens):
                        self._ui_note("--format requires a value")
                        return True
                    fmt = tokens[i + 1]; i += 2
                elif tok in ("--output", "-o"):
                    if i + 1 >= len(tokens):
                        self._ui_note("--output requires a value")
                        return True
                    output = tokens[i + 1]; i += 2
                elif tok == "--show-cycles":
                    show_cycles = True; i += 1
                elif tok in ("--module", "-m"):
                    if i + 1 >= len(tokens):
                        self._ui_note("--module requires a value")
                        return True
                    module = tokens[i + 1]; i += 2
                elif tok.startswith("-"):
                    self._ui_note(f"unknown option: {tok}")
                    return True
                elif directory == ".":
                    directory = tok; i += 1
                else:
                    self._ui_note(f"unexpected argument: {tok}")
                    return True

            try:
                output_path, size_bytes = _run_graph(
                    directory=directory,
                    format=fmt,
                    output=output,
                    show_cycles=show_cycles,
                    module=module,
                    cwd=self.config.cwd,
                )
                self._ui_note(f"graph saved: {output_path}  ({size_bytes} bytes)")
            except Exception as exc:
                self._ui_note(f"error generating graph: {exc}")
                if os.getenv("TIAGA_DEBUG"):
                    import traceback
                    traceback.print_exc()

        else:
            self._ui_note(f"unknown command: {cmd}  (try /help)")

        return True


# ── Graph runner ───────────────────────────────────────────────────────────────

def _run_graph(
    directory: str,
    format: str = "summary",
    output: str | None = None,
    show_cycles: bool = False,
    module: str | None = None,
    cwd: Path | None = None,
) -> tuple[str, int]:
    base_dir   = (cwd or Path.cwd()).resolve()
    target_dir = (base_dir / directory).resolve()

    if not target_dir.exists():
        raise FileNotFoundError(f"directory not found: {target_dir}")

    builder = DependencyGraphBuilder(root_path=str(target_dir))
    builder.analyze_directory()
    builder.find_cycles()

    if module:
        builder.filter_module(module)

    formatters = {
        "summary": builder.get_summary,
        "json":    builder.to_json,
        "dot":     builder.to_dot,
        "md":      builder.to_markdown,
        "tree":    builder.to_tree,
    }
    if format not in formatters:
        raise ValueError(f"unknown format '{format}'. valid: {', '.join(formatters)}")

    content = formatters[format]()

    if output:
        out_path = Path(output)
    else:
        graphs_dir = base_dir / "project_graph"
        graphs_dir.mkdir(parents=True, exist_ok=True)
        ext = {"json": "json", "dot": "dot", "md": "md", "tree": "txt"}.get(format, "txt")
        out_path = graphs_dir / f"graph.{ext}"

    out_path.write_text(content if isinstance(content, str) else str(content))
    return str(out_path), out_path.stat().st_size


# ── Entry point ────────────────────────────────────────────────────────────────

@click.group(
    invoke_without_command=True,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.option("--cwd", "-c", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.pass_context
def main(ctx: click.Context, cwd: Path | None = None):
    """Tiaga — AI coding assistant."""
    if ctx.invoked_subcommand:
        return

    prompt = " ".join(ctx.args).strip() if getattr(ctx, "args", None) else None
    if not prompt:
        prompt = None

    try:
        config = load_config(cwd, require_api=bool(prompt))
    except ConfigError as exc:
        click.echo(f"config error: {exc}", err=True)
        raise SystemExit(1)
    except Exception as exc:
        click.echo(f"startup error: {exc}", err=True)
        raise SystemExit(1)

    cli = CLI(config)

    if prompt:
        result = asyncio.run(cli.run_single(prompt))
        if result is None:
            raise SystemExit(1)
    else:
        asyncio.run(cli.run_interactive())


if __name__ == "__main__":
    main()
