import os
from pathlib import Path
import sys
import time
from typing import Any
from tiaga.agent.persistence import PersistenceManager, SessionSnapshot
from tiaga.agent.session import Session
from tiaga.config.config import ApprovalPolicy, Config
from tiaga.config.loader import load_config, update_config

from tiaga.utils.erors import ConfigError
from tiaga.ui.render import TUI,_get_console
from tiaga.tracing.trace import Trace
import click
import asyncio
from tiaga.agent.agent import Agent,AgentEventType
#main.py
console = _get_console()

LOGO = """\
████████╗██╗ █████╗  ██████╗  █████╗ 
╚══██╔══╝██║██╔══██╗██╔════╝ ██╔══██╗
   ██║   ██║███████║██║  ███╗███████║
   ██║   ██║██╔══██║██║   ██║██╔══██║
   ██║   ██║██║  ██║╚██████╔╝██║  ██║
   ╚═╝   ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝
"""



class CLI():
    def __init__(self, config:Config):
        self.config = config
        self.agent:Agent|None = None
        self.tui = TUI(console=console,config=config)
        self.persistence_manager = PersistenceManager()
        self.assistant_streaming = False
        self._pending_plan_steps: dict[int, dict[str, str]] = {}
        self._active_plan_step: dict[str, str] | None = None
        self._response_start_time: float | None = None
        self._response_latency: float | None = None

    def _ui_note(self, text: str) -> None:
        self.tui.post_message(text)

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
        )

    def _persist_session(self, announce: bool = False) -> None:
        snapshot = self._build_session_snapshot()
        if snapshot is None:
            return
        try:
            self.persistence_manager.save_session(snapshot)
            if announce:
                self._ui_note(f"Session saved: {snapshot.session_id}")
        except Exception as exc:
            console.log(f"[warning]Failed to save session {snapshot.session_id}:[/warning] {exc}")
            if announce:
                self._ui_note(f"Failed to save session: {exc}")
    def get_tool_kind(self, tool_name):
        if not self.agent:
            return None
        tool = self.agent.session.tool_registry.get(tool_name)
        if tool:
            return tool.tool_kind.value
        return None

    def _format_plan_items(self, plan_steps) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        for idx, step in enumerate(plan_steps):
            status = "active" if idx == 0 else "pending"
            items.append((f"{step.step}. {step.task} ({step.tool})", status))
        return items

    def _clear_plan(self) -> None:
        self._pending_plan_steps = {}
        self._active_plan_step = None

    def _dispatch_next_plan_step(self) -> None:
        if self._active_plan_step is not None:
            return
        if not self._pending_plan_steps:
            return
        next_key = sorted(self._pending_plan_steps.keys())[0]
        next_step = self._pending_plan_steps.pop(next_key)
        next_step["status"] = "active"
        self._active_plan_step = next_step
        self.tui.post_plan([(next_step["label"], next_step["status"])])

    def _set_plan(self, plan_steps) -> None:
        self._clear_plan()
        for idx, step in enumerate(plan_steps, start=1):
            if isinstance(step, dict):
                raw_step = step.get("step", idx)
                task = step.get("task", "")
                tool = step.get("tool", "")
            else:
                raw_step = getattr(step, "step", idx)
                task = getattr(step, "task", "")
                tool = getattr(step, "tool", "")

            step_number = int(raw_step or idx)
            while step_number in self._pending_plan_steps:
                step_number += 1
            self._pending_plan_steps[step_number] = (
                {
                    "label": f"{step_number}. {task} ({tool})",
                    "tool": (tool or "").strip(),
                    "status": "pending",
                }
            )
        self._dispatch_next_plan_step()

    def _track_tool_start(self, tool_name: str) -> None:
        if self._active_plan_step is None:
            self._dispatch_next_plan_step()
        if self._active_plan_step is None:
            return
        if self._active_plan_step["tool"] == tool_name:
            return

    def _track_tool_end(self, tool_name: str, success: bool) -> None:
        if self._active_plan_step is None or not success:
            return
        if self._active_plan_step["tool"] != tool_name:
            return
        self._active_plan_step["status"] = "done"
        self.tui.post_plan([(self._active_plan_step["label"], self._active_plan_step["status"])])
        self._active_plan_step = None
        self._dispatch_next_plan_step()

    async def _planning_spinner(self, stop_event: asyncio.Event) -> None:
        frames = ["◜", "◠", "◝", "◞", "◡", "◟"]
        idx = 0
        while not stop_event.is_set():
            self.tui.set_current_assistant_text(frames[idx % len(frames)])
            idx += 1
            await asyncio.sleep(0.12)

    async def run_interactive(self):

        self.tui.print_welcome(LOGO,lines=[
            f"model:{self.config.model_name} ",
            f"cwd:{self.config.cwd} ",
            f"command: /help /exit /config /approval /model"
        ])
        async with Agent(self.config,self.tui.handle_confirmation) as agent:
            self.agent = agent
            while True:
                try:
                    user_input = self.tui.prompt_user().strip()
                    if user_input.startswith('/'):
                        should_continue = await  self.handle_command(user_input)
                        if not should_continue:
                            break
                        continue
                    if not self.check_api():
                        self._ui_note("Before Using first set base_url(/base_url) , api_key(/api_key) and model name(/model name)")
                        continue
                        
                    if not user_input:
                        continue
                    self.tui.add_user_message(user_input)
                    Trace.trace_before_agent(user_message=user_input)
                    final_response = await self._process_message(user_input)
                    Trace.trace_after_agent(
                        user_message=user_input,
                        final_response=final_response or "",
                        latency=self._response_latency,
                        turn_count=self.agent.session.turn_count if self.agent and self.agent.session else None,
                        token_usage=self.agent.session.context_manager.total_usage if self.agent and self.agent.session and self.agent.session.context_manager else None
                    )
                    self._persist_session()
                except KeyboardInterrupt:
                    self._ui_note("Use /exit to quit.")
                except EOFError:
                    break           
            self._persist_session()
            self._ui_note("Goodbye.")
        


    async def run_single(self,message):
        async with Agent(self.config) as agent:
            self.agent = agent
            if message.startswith("/"):
                should_continue = await self.handle_command(message)
                return "" if should_continue else None
            if not self.check_api():
                self.tui.stream_final_answer("Before Using first set base_url(/base_url) , api_key(/api_key) and model name(/model name)")
                return
            Trace.trace_before_agent(user_message=message)
            response = await self._process_message(message)
            Trace.trace_after_agent(
                user_message=message,
                final_response=response or "",
                latency=self._response_latency,
                turn_count=self.agent.session.turn_count if self.agent and self.agent.session else None,
                token_usage=self.agent.session.context_manager.total_usage if self.agent and self.agent.session and self.agent.session.context_manager else None
            )
            self._persist_session()
            return response

    

    def check_api(self):
        if self.config.api_key_value == "set_api_key":
            return False
        if self.config.base_url_value == "set_base_url":
            return False
        if self.config.model.name == "":
            return False
        return True
  
        

    async def _process_message(self,message):
        if not self.agent:
            return None
        self._response_start_time = time.time()
        self.agent.session.increment_turn()
        final_response = None
        plan_phase_done = False
        final_started = False
        if not self.assistant_streaming:
            self.assistant_streaming = True
            self.tui.begin_streaming("Thinking...")
        async for event in self.agent.run(message):


            if event.type == AgentEventType.TOOL_CALL_START:
                plan_phase_done = True
                tool_name = event.data.get("name","unknown")
                self._track_tool_start(tool_name)
                tool_kind = self.get_tool_kind(tool_name=tool_name)
                self.tui.render_tool_call_start(event.data.get('call_id',""), tool_kind, tool_name, event.data.get("arguments",{}))
                # Give the UI thread a moment to paint the running tool card
                # before potentially blocking tool execution begins.
                await asyncio.sleep(0.03)

            elif event.type == AgentEventType.TOOL_CALL_END:

                tool_name = event.data.get("name","unknown")
                self._track_tool_end(tool_name, event.data.get("success", False))
                tool_kind = self.get_tool_kind(tool_name=tool_name)
                self.tui.render_tool_call_end(
                    event.data.get("call_id",""),
                    tool_kind,
                    tool_name,
                    event.data.get("success",False),
                    event.data.get("error",""),
                    event.data.get("display_output", event.data.get("output","")),
                    event.data.get("metadata",{}),
                    event.data.get("diff"),
                    event.data.get("truncated",False),
                    event.data.get("exit_code")
                )
            elif event.type == AgentEventType.PLAN:
                steps = event.data.get("steps", [])
                if steps:
                    self._set_plan(steps)
                else:
                    self._clear_plan()

                plan_phase_done = True
            elif event.type == AgentEventType.TEXT_DELTA:
                content = event.data.get("content", "")

                # 🔥 Only switch AFTER planning/tools phase
                if plan_phase_done and not final_started:
                    final_started = True

                    if self.assistant_streaming:
                        self.tui.end_assistance()
                        self.assistant_streaming = False

                    self.tui.start_final_answer()

                # If final started → stream there
                if final_started:
                    self.tui.stream_final_answer(content)
                else:
                    # still thinking phase
                    self.tui.stream_assistant_delta(content)


            elif event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content", "")

                if final_started:
                    self.tui.end_final_answer()
                elif self.assistant_streaming:
                    self.tui.end_assistance()
                    self.assistant_streaming = False
            


            elif event.type == AgentEventType.AGENT_ERROR:
                error = event.data.get("error", "Unknown error")

                if self.assistant_streaming:
                    # overwrite the "Thinking..." block
                    self.tui.stream_assistant_delta(f"❌ Error: {error}")
                    self.tui.end_assistance()
                    self.assistant_streaming = False
                else:
                    self._ui_note(f"Error: {error}") 
            elif event.type == AgentEventType.AGENT_END:
                usage_data = event.data.get("usage")
                if self.assistant_streaming:
                    self.tui.end_assistance()
                    self.assistant_streaming = False
        
        # Calculate and display latency
        if self._response_start_time:
            self._response_latency = time.time() - self._response_start_time
            latency_text = f"\n\n---\n⏱️  Response latency: {self._response_latency:.2f}s"
            self.tui.stream_final_answer(latency_text)
            
            # Collect token usage if available
            token_usage = None
            if self.agent and self.agent.session and self.agent.session.context_manager:
                token_usage = self.agent.session.context_manager.total_usage
            
            # Trace the response latency
            turn_count = self.agent.session.turn_count if self.agent and self.agent.session else None
            Trace.trace_response_latency(
                latency=self._response_latency,
                turn_count=turn_count,
                token_usage=token_usage,
                success=True
            )

        return final_response
    async def handle_command(self,command:str)->bool:
        command = command.strip()
        parts = command.split(maxsplit=1)
        cmd_name = parts[0].lower()
        cmd_args = parts[1] if len(parts) > 1 else ""


        if cmd_name in ["/exit","/quit","/q"]:
            self._persist_session()
            self._ui_note("Exiting Tiaga...")
            self.tui.shutdown()
            return False
        elif cmd_name == "/help":
            self.tui.show_help()
        elif cmd_name == "/clear":
            self.agent.session.context_manager.clear() 
            self._ui_note("Conversation history was cleared.")
        elif cmd_name == "/config":
            self._ui_note(
                "Current Configuration\n"
                f"Model: {self.config.model_name}\n"
                f"Temperature: {self.config.temperature}\n"
                f"Approval: {self.config.approval.value}\n"
                f"Working Dir: {self.config.cwd}\n"
                f"Max Turns: {self.config.max_turns}\n"
                f"Hooks Enabled: {self.config.hooks_enabled}"
            )
        elif cmd_name == "/model":
            if cmd_args:
                self.config.model.name = cmd_args
                update_config({"model": {"name": cmd_args}})
                self._ui_note(f"Model changed to: {cmd_args}")
            self._ui_note(f"Current model: {self.config.model_name}")
        
        elif cmd_name == "/api_key":
            if cmd_args:
                self.config.api_key_value = cmd_args
                update_config({"api_key": cmd_args})
                self._ui_note(f"API key updated successfully")
            else:
                self._ui_note(f"Current API key: {'*' * len(self.config.api_key_value) if self.config.api_key_value != 'set_api_key' else 'not set'}")
        
        elif cmd_name == "/base_url":
            if cmd_args:
                self.config.base_url_value = cmd_args
                update_config({"base_url": cmd_args})
                self._ui_note(f"Base URL updated to: {cmd_args}")
            else:
                self._ui_note(f"Current base URL: {self.config.base_url_value}")

        elif cmd_name == "/approval":
            if cmd_args:
                try:
                    approval = ApprovalPolicy(cmd_args)
                    update_config({"approval": approval.value})
                    self.config.approval = approval
                    self._ui_note(f"Approval policy changed to: {cmd_args}")
                except:
                    self._ui_note(f"Incorrect approval policy: {cmd_args}")
                    self._ui_note(f"Valid options: {', '.join(p for p in ApprovalPolicy)}")
            else:
                self._ui_note(f"Current approval: {self.config.approval.value}")
        
        elif cmd_name == "/stats":
            stats = self.agent.session.get_stats()
            lines = [f"{k}: {value}" for k, value in stats.items()]
            self._ui_note("Stats\n" + "\n".join(lines))

        elif cmd_name == "/tools":
            tools = self.agent.session.tool_registry.get_tools()
            tool_lines = [tool.name for tool in tools]
            self._ui_note(f"Available tools ({len(tools)})\n" + "\n".join(tool_lines))

        elif cmd_name == "/mcp":
            mcp_servers = self.agent.session.tool_registry.mcp_tools
            self._ui_note(f"MCP Servers ({len(mcp_servers)})")
            for server in mcp_servers:
                self._ui_note(f"• {server.name}")
        elif cmd_name == "/save":
            self._persist_session(announce=True)
        elif cmd_name =="/sessions":
            persistence_manager = PersistenceManager()
            sessions = persistence_manager.list_sessions()
            self._ui_note("Saved Session")
            for s in sessions:
              self._ui_note(
                f"• {s['session_id']} "
                f"updated: {s['updated_at']}  turns: {s['turn_count']}"
                    )
        elif cmd_name =="/checkpoints":
            persistence_manager = PersistenceManager()
            if not cmd_args:
                self._ui_note("session args are required to list checkpoints")
            else :
                checkpoints = persistence_manager.list_checkpoints(cmd_args.strip())
                self._ui_note("Saved Checkpoints")
                for s in checkpoints:
                    self._ui_note(
                        s
                            )
        elif cmd_name == "/resume":
            if not cmd_args:
                self._ui_note("Usage: /resume <session_id>")
            else :
                persistence_manager = PersistenceManager()

                snapshot = persistence_manager.load_session(cmd_args.strip())
                if not snapshot:
                    self._ui_note("Session does not exist")
                else :
                    session = Session(config=self.config)
                    await session.initialize()
                    session.created = snapshot.created_at
                    session.session_id = snapshot.session_id
                    session.updated = snapshot.updated_at
                    session.turn_count = snapshot.turn_count
                    session.context_manager.total_usage = snapshot.total_usage
                    for msg in snapshot.messages:
                        if msg.get("role") == "system":
                            continue
                        elif msg['role'] == "user":
                            session.context_manager.add_user_message(msg.get("content",""))
                        elif msg['role'] == "assistant":
                            session.context_manager.add_assistant_message(msg.get("content",""),msg.get("tool_calls"))
                        elif msg["role"] == "tool":
                            session.context_manager.add_tool_message(msg.get("tool_call_id",""),msg.get("content",""))
                    await self.agent.session.mcp_manager.shutdown()
                    await self.agent.session.client.close_client()

                    self.agent.session = session
                    self._ui_note(f"Session resumed {session.session_id}")

        elif cmd_name == "/checkpoint":
            session_snapshot = self._build_session_snapshot()
            if session_snapshot is None:
                self._ui_note("No active session to checkpoint.")
            else:
                checkpoint_id = self.persistence_manager.save_checkpoint(session_snapshot)
                self._ui_note(f"checkpoint saved {checkpoint_id}")
        elif cmd_name == "/restore":
            if not cmd_args:
                self._ui_note("Usage: /restore <session_id>")
            else :
                persistence_manager = PersistenceManager()

                snapshot = persistence_manager.load_checkpoint(cmd_args.strip())
                if not snapshot:
                    self._ui_note("Session does not exist")
                else :
                    session = Session(config=self.config)
                    await session.initialize()
                    session.created = snapshot.created_at
                    session.session_id = snapshot.session_id
                    session.updated = snapshot.updated_at
                    session.turn_count = snapshot.turn_count
                    session.context_manager.total_usage = snapshot.total_usage
                    for msg in snapshot.messages:
                        if msg.get("role") == "system":
                            continue
                        elif msg['role'] == "user":
                            session.context_manager.add_user_message(msg.get("content",""))
                        elif msg['role'] == "assistant":
                            session.context_manager.add_assistant_message(msg.get("content",""),msg.get("tool_calls"))
                        elif msg["role"] == "tool":
                            session.context_manager.add_tool_message(msg.get("tool_call_id",""),msg.get("content",""))
                    await self.agent.session.mcp_manager.shutdown()
                    await self.agent.session.client.close_client()

                    self.agent.session = session
                    self._ui_note(f"Session resumed {session.session_id} and checkpoint {cmd_args}")


        else :
            self._ui_note(f"Unknown command {cmd_name}")
        return True

                
               



@click.command()
@click.argument("prompt",required = False)
@click.option("--cwd","-c",type=click.Path(exists=True,file_okay=False,path_type=Path),help="current working dir")
def main(prompt:str|None = None,cwd:Path|None = None):



    try:
        config = load_config(cwd)
    except ConfigError as e:
        console.log(f"\n[error]Config error:[/error] {e}")
        raise SystemExit(1)
    except Exception as e :
        console.log(f"\n[error]Unexpected startup error:[/error] {e}")
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
