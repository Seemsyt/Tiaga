import os
from pathlib import Path
import sys
from typing import Any
from tiaga.agent.persistence import PersistenceManager, SessionSnapshot
from tiaga.agent.session import Session
from tiaga.config.config import ApprovalPolicy, Config
from tiaga.config.loader import load_config, update_config

from tiaga.utils.erors import ConfigError
from tiaga.ui.render import TUI,_get_console
import click
import asyncio
from tiaga.client.llm_client import LLM_client
from tiaga.agent.agent import Agent,AgentEventType

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
        self.assistant_streaming = False
        self._pending_plan_steps: dict[int, dict[str, str]] = {}
        self._active_plan_step: dict[str, str] | None = None

    def _ui_note(self, text: str) -> None:
        self.tui.post_message(text)
        




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
            step_number = int(getattr(step, "step", idx) or idx)
            while step_number in self._pending_plan_steps:
                step_number += 1
            self._pending_plan_steps[step_number] = (
                {
                    "label": f"{step.step}. {step.task} ({step.tool})",
                    "tool": (step.tool or "").strip(),
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
            self.tui.set_streaming_text(frames[idx % len(frames)])
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
                    if not user_input:
                        continue
                    self._ui_note(f"You: {user_input}")
                    tool_names = [tool.name for tool in self.agent.session.tool_registry.get_tools()]
                    spinner_stop = asyncio.Event()
                    spinner_task: asyncio.Task | None = None
                    if not self.assistant_streaming:
                        self.assistant_streaming = True
                        self.tui.begin_streaming("◜")
                        spinner_task = asyncio.create_task(self._planning_spinner(spinner_stop))
                    try:
                        plan = await asyncio.wait_for(
                            self.agent.session.planner.create_plan(
                                user_query=user_input,
                                available_tools=tool_names,
                            ),
                            timeout=1.5,
                        )
                        if plan:
                            self._set_plan(plan)
                        else:
                            self._clear_plan()
                    except TimeoutError:
                        self._clear_plan()
                    except Exception:
                        self._clear_plan()
                    finally:
                        spinner_stop.set()
                        if spinner_task:
                            await spinner_task
                        if self.assistant_streaming:
                            self.tui.end_assistance()
                            self.assistant_streaming = False
                    await self._process_message(user_input)
                except KeyboardInterrupt:
                    self._ui_note("Use /exit to quit.")
                except EOFError:
                    break           
            self._ui_note("Goodbye.")
        


    async def run_single(self,message):
        async with Agent(self.config) as agent:
            self.agent = agent
            if message.startswith("/"):
                should_continue = await self.handle_command(message)
                return "" if should_continue else None
            return await self._process_message(message)

    

    
            
    async def _process_message(self,message):
        if not self.agent:
            return None
        final_response = None
        if not self.assistant_streaming:
            self.assistant_streaming = True
            self.tui.begin_streaming("Thinking...")
        async for event in self.agent.run(message):


            if event.type == AgentEventType.TOOL_CALL_START:
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

            elif event.type == AgentEventType.TEXT_DELTA:

                content = event.data.get("content","")
                self.tui.stream_assistant_delta(content=content)


            elif event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content","")
                if self.assistant_streaming:
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
  


        return final_response
    async def handle_command(self,command:str)->bool:
        cmd = command.lower().strip()
        parts = cmd.split(maxsplit=1)
        cmd_name = parts[0]
        cmd_args = parts[1] if len(parts) > 1 else ""


        if cmd_name in ["/exit","/quit","/q"]:
            self._ui_note("Exiting Tiaga...")
            self.tui.shutdown()
            return False
        elif cmd_name == "/help":
            self.tui.show_help()
        elif cmd_name == "/clear":
            self.agent.session.context_manager.clear() 
            self.agent.session.loop_detector.clear_history()
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
                self.config.model_name = cmd_args
                self._ui_note(f"Model changed to: {cmd_args}")
            self._ui_note(f"Current model: {self.config.model_name}")

        elif cmd_name == "/approval":
            if cmd_args:
                try:
                    approval = ApprovalPolicy(cmd_args)
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
            mcp_servers = self.agent.session.tool_registry.getmcp
            self._ui_note(f"MCP Servers ({len(mcp_servers)})")
            for server in mcp_servers:
                self._ui_note(f"• {server.name}")
        elif cmd_name == "/save":
            persistence_manager = PersistenceManager()
            session_snapshot =SessionSnapshot(
                session_id=self.agent.session.session_id,
                created_at=self.agent.session.created,
                updated_at=self.agent.session.updated,
                turn_count=self.agent.session.turn_count,
                messages=self.agent.session.context_manager.get_messages(),
                total_usage=self.agent.session.context_manager.total_usage,
            )
            persistence_manager.save_session(session_snapshot)
            self._ui_note(f"Session saved: {self.agent.session.session_id}")
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
                    await self.agent.session.mcp_manager.Shoutdown()
                    await self.agent.session.client.close_client()
                    
                    self.agent.session = session
                    self._ui_note(f"Session resumed {session.session_id}")

        elif cmd_name == "/checkpoint":
            persistence_manager = PersistenceManager()
            session_snapshot =SessionSnapshot(
                session_id=self.agent.session.session_id,
                created_at=self.agent.session.created,
                updated_at=self.agent.session.updated,
                turn_count=self.agent.session.turn_count,
                messages=self.agent.session.context_manager.get_messages(),
                total_usage=self.agent.session.context_manager.total_usage,
            )
            checkpoint_id = persistence_manager.save_checkpoint(session_snapshot)
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
                    await self.agent.session.mcp_manager.Shoutdown()
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
