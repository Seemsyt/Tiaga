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




class CLI():
    def __init__(self, config:Config):
        self.config = config
        self.agent:Agent|None = None
        self.tui = TUI(console=console,config=config)
        self.assistant_streaming = False

        

    def get_tool_kind(self,tool_name):
        tool= self.agent.session.tool_registry.get(tool_name)
        if tool:
            tool_kind= tool.tool_kind.value
            return tool_kind
        return None

    async def run_interactive(self):

        self.tui.print_welcome('Tiaga',lines=[
            f"model:{self.config.model_name} ",
            f"cwd:{self.config.cwd} ",
            f"command: /help /exit /config /approval /model"
        ])
        async with Agent(self.config,self.tui.handle_confirmation) as agent:
            self.agent = agent
            while True:
                try:
                    user_input = console.input(f"\n[user]>[/user]").strip()
                    if user_input.lower().strip() == "/exit":
                        break
                    if user_input.startswith('/'):
                        should_continue = await  self.handle_command(user_input)
                        if not should_continue:
                            break
                        continue
                    if not user_input:
                        continue
                    await self._process_message(user_input)
                except KeyboardInterrupt:
                    console.print(f"\n[dim] use /exit to quit[/dim]")
                except EOFError:
                    break           
            console.print(f"\n[dim]Goodbye[/dim]")
        


    async def run_single(self,message):
        async with Agent(self.config) as agent:
            self.agent = agent
            if await self._handle_local_command(message):
                return ""
            return await self._process_message(message)

    

    
            
    async def _process_message(self,message):
        if not self.agent:
            return None
        final_response = None
        async for event in self.agent.run(message):


            if event.type == AgentEventType.TOOL_CALL_START:
                tool_name = event.data.get("name","unknown")
                tool_kind = self.get_tool_kind(tool_name=tool_name)
                self.tui.render_tool_call_start(event.data.get('call_id',""), tool_kind, tool_name, event.data.get("arguments",{}))

            elif event.type == AgentEventType.TOOL_CALL_END:

                tool_name = event.data.get("name","unknown")
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
                if not self.assistant_streaming:
                    self.assistant_streaming = True
                    self.tui.begin_streaming()
                self.tui.stream_assistant_delta(content=content)


            elif event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content","")
                if self.assistant_streaming:
                    self.tui.end_assistance()
                    self.assistant_streaming = False


            elif event.type == AgentEventType.AGENT_ERROR:
                error = event.data.get("error","Unknown error")
                console.log(f"\n[error]Error:{error}[/error]")
                if self.assistant_streaming:
                    self.tui.end_assistance()
                    self.assistant_streaming = False 
            elif event.type == AgentEventType.AGENT_END:
                usage_data = event.data.get("usage")
  


        return final_response
    async def handle_command(self,command:str)->bool:
        cmd = command.lower().strip()
        parts = cmd.split(maxsplit=1)
        cmd_name = parts[0]
        cmd_args = parts[1] if len(parts) > 1 else ""


        if cmd_name in ["/exit","/quit","/q"]:
            return False
        
        elif cmd_name == "/help":
            self.tui.show_help()
        elif cmd_name == "/clear":
            self.agent.session.context_manager.clear() 
            self.agent.session.loop_detector.clear_history()
            console.print(f"[success]Conversation History was cleared[/success]")
        elif cmd_name == "/config":
            console.print("\n[bold]Current Configuration[/bold]")
            console.print(f"  Model: {self.config.model_name}")
            console.print(f"  Temperature: {self.config.temperature}")
            console.print(f"  Approval: {self.config.approval.value}")
            console.print(f"  Working Dir: {self.config.cwd}")
            console.print(f"  Max Turns: {self.config.max_turns}")
            console.print(f"  Hooks Enabled: {self.config.hooks_enabled}")
        elif cmd_name == "/model":
            if cmd_args:
                self.config.model_name = cmd_args
                console.print(f"[success]Model changed to: {cmd_args} [/success]")
            console.print(f"Current model : {self.config.model_name}")

        elif cmd_name == "/approval":
            if cmd_args:
                try:
                    approval = ApprovalPolicy(cmd_args)
                    self.config.approval = approval
                    console.print(
                        f"[success]Approval policy changed to: {cmd_args} [/success]"
                    )
                except:
                    console.print(
                        f"[error]Incorrect approval policy: {cmd_args} [/error]"
                    )
                    console.print(
                        f"Valid options: {', '.join(p for p in ApprovalPolicy)}"
                    )
            else:
                console.print(f"Current approval: {self.config.approval.value}")
        
        elif cmd_name == "/stats":
            stats = self.agent.session.get_stats()
            console.print("\n[bold]Stats statics [/bold]")
            
            for k,value in stats.items():
                console.print(f" {k}: {value}") 

        elif cmd_name == "/tools":
            tools = self.agent.session.tool_registry.get_tools()
            console.print(f"\n[bold]Available tools ({len(tools)}) [/bold]")
            for tool in tools:
                console.print(f"  • {tool.name}")

        elif cmd_name == "/mcp":
            mcp_servers = self.agent.session.tool_registry.getmcp
            console.print(f"\n[bold]MCP Servers ({len(mcp_servers)}) [/bold]")
            for server in mcp_servers:
                console.print(f" • {server.name}")
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
            console.print(f"[success] session saved {self.agent.session.session_id} [/success]")
        elif cmd_name =="/sessions":
            persistence_manager = PersistenceManager()
            sessions = persistence_manager.list_sessions()
            console.print(f"[bold] Saved Session [/bold]")
            for s in sessions:
              console.print(
                f"[success]•{s['session_id']}[/success] "
                f"updated: {s['updated_at']}  turns: {s['turn_count']}"
                    )
        elif cmd_name =="/checkpoints":
            persistence_manager = PersistenceManager()
            if not cmd_args:
                console.log(f"[error]session args are required to list checkpoint [/error]")
            else :
                checkpoints = persistence_manager.list_checkpoints(cmd_args.strip())
                console.print(f"[bold] Saved Checkpoints [/bold]")
                for s in checkpoints:
                    console.print(
                        s
                            )
        elif cmd_name == "/resume":
            if not cmd_args:
                console.print(f"[error]Usage: /resume <session_id> [/error]")
            else :
                persistence_manager = PersistenceManager()

                snapshot = persistence_manager.load_session(cmd_args.strip())
                if not snapshot:
                    console.print(f"[error]Session does not exist [/error]")
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
                    console.print(f"[success]Session resumed {session.session_id} [/success]")

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
            console.print(f"[success] checkpoint saved {checkpoint_id} [/success]")
        elif cmd_name == "/restore":
            if not cmd_args:
                console.print(f"[error]Usage: /restore <session_id> [/error]")
            else :
                persistence_manager = PersistenceManager()

                snapshot = persistence_manager.load_checkpoint(cmd_args.strip())
                if not snapshot:
                    console.print(f"[error]Session does not exist [/error]")
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
                    console.print(f"[success]Session resumed {session.session_id} and checkpoint {cmd_args} [/success]")


        else :
            console.print(f"[error] Unknown command {cmd_name}[/error]")
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
