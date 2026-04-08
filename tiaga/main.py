from pathlib import Path
import sys
from typing import Any
from tiaga.config.loader import load_config, update_config
from tiaga.utils.erors import ConfigError
from tiaga.ui.render import TUI,_get_console
import click
import asyncio
from tiaga.client.llm_client import LLM_client
from tiaga.agent.agent import Agent,AgentEventType
import shlex
console = _get_console()



class CLI():
    def __init__(self, config):
        self.config = config
        self.agent:Agent|None = None
        self.tui = TUI(console=console,config=config)
        self.assistant_streaming = False
        self.session_usage:dict[str,int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
        }
        self.usage_by_model:dict[str,dict[str,int]] = {}

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
        async with Agent(self.config) as agent:
            self.agent = agent
            while True:
                try:
                    user_input = console.input(f"\n[user]>[/user]").strip()
                    if user_input.lower().strip() == "/exit":
                        break
                    if not user_input:
                        continue
                    if await self._handle_local_command(user_input):
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

    def _mask_secret(self,value:str|None)->str:
        if not value:
            return "(not set)"
        if len(value) <= 8:
            return "*" * len(value)
        return f"{value[:4]}...{value[-4:]}"

    def _print_config_help(self)->None:
        console.print("[info]/config usage:[/info]")
        console.print("[dim]- /config show[/dim]")
        console.print("[dim]- /config model <model_name>[/dim]")
        console.print("[dim]- /config base_url <url>[/dim]")
        console.print("[dim]- /config api_key <key>[/dim]")
        console.print("[dim]- /model[/dim]")
        console.print("[dim]- /model <model_name>[/dim]")

    def _show_config(self)->None:
        console.print("[info]Current config:[/info]")
        console.print(f"[dim]model:[/dim] {self.config.model_name or '(not set)'}")
        console.print(f"[dim]base_url:[/dim] {self.config.base_url or '(not set)'}")
        console.print(f"[dim]api_key:[/dim] {self._mask_secret(self.config.api_key)}")

    def _show_model_usage(self)->None:
        usage = self.session_usage
        console.print("[info]Model usage:[/info]")
        console.print(f"[dim]model:[/dim] {self.config.model_name or '(not set)'}")
        console.print(f"[dim]prompt_tokens:[/dim] {usage.get('prompt_tokens', 0)}")
        console.print(f"[dim]completion_tokens:[/dim] {usage.get('completion_tokens', 0)}")
        console.print(f"[dim]total_tokens:[/dim] {usage.get('total_tokens', 0)}")
        console.print(f"[dim]cached_tokens:[/dim] {usage.get('cached_tokens', 0)}")
        if self.usage_by_model:
            console.print("[info]Per-model usage:[/info]")
            for model_name, model_usage in self.usage_by_model.items():
                console.print(
                    f"[dim]{model_name}[/dim] "
                    f"prompt={model_usage.get('prompt_tokens',0)} "
                    f"completion={model_usage.get('completion_tokens',0)} "
                    f"total={model_usage.get('total_tokens',0)} "
                    f"cached={model_usage.get('cached_tokens',0)}"
                )

    def _update_session_usage(self,usage_data:dict[str,Any]|None)->None:
        if not isinstance(usage_data,dict):
            return
        for key in self.session_usage:
            value = usage_data.get(key)
            if isinstance(value,int):
                self.session_usage[key] += value
        model_name = self.config.model_name or "(not set)"
        model_usage = self.usage_by_model.setdefault(
            model_name,
            {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cached_tokens": 0,
            },
        )
        for key in model_usage:
            value = usage_data.get(key)
            if isinstance(value,int):
                model_usage[key] += value

    async def _handle_local_command(self,message:str)->bool:
        stripped = message.strip()
        if not stripped.startswith("/"):
            return False

        try:
            parts = shlex.split(stripped)
        except ValueError as e:
            console.print(f"[error]Invalid command:[/error] {e}")
            return True

        if not parts:
            return False

        command = parts[0].lower()
        if command in {"/help"}:
            self._print_config_help()
            return True

        if command in {"/model"}:
            if len(parts) == 1:
                self._show_model_usage()
                return True
            parts = ["/config", "model", " ".join(parts[1:])]
            command = "/config"

        if command not in {"/config", "/congig"}:
            return False

        if len(parts) == 1:
            self._print_config_help()
            return True

        action = parts[1].lower()
        if action in {"help", "-h", "--help"}:
            self._print_config_help()
            return True
        if action == "show":
            self._show_config()
            return True

        if len(parts) < 3:
            console.print("[error]Missing value.[/error] Use /config help")
            return True

        value = " ".join(parts[2:]).strip()
        if not value:
            console.print("[error]Value cannot be empty.[/error]")
            return True

        updates:dict[str,Any]
        if action in {"model", "model_name"}:
            self.config.model_name = value
            updates = {"model": {"name": value}}
            display_value = value
        elif action in {"base_url", "url", "baseurl"}:
            self.config.base_url = value
            updates = {"base_url": value}
            display_value = value
        elif action in {"api_key", "apikey", "key"}:
            self.config.api_key = value
            updates = {"api_key": value}
            display_value = self._mask_secret(value)
        else:
            console.print(f"[error]Unknown config key:[/error] {action}")
            self._print_config_help()
            return True

        try:
            path = update_config(updates,cwd=self.config.cwd)
        except Exception as e:
            console.print(f"[error]Failed to persist config:[/error] {e}")
            return True

        console.print(f"[success]Updated {action}[/success] -> {display_value}")
        console.print(f"[dim]Saved to {path}[/dim]")
        return True
            
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
                self._update_session_usage(usage_data)


        return final_response

                
               



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
