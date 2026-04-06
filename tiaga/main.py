from pathlib import Path
import sys
from typing import Any
from tiaga.config.loader import load_config
from tiaga.utlis.erors import ConfigError
from ui.render import TUI,_get_console
import click
import asyncio
from client.llm_client import LLM_client
from agent.agent import Agent,AgentEventType
console = _get_console()



class CLI():
    def __init__(self, config):
        self.config = config
        self.agent:Agent|None = None
        self.tui = TUI(console=console,config=config)
        self.assistant_streaming = False

    def get_tool_kind(self,tool_name):
        tool= self.agent.tool_registry.get(tool_name)
        if tool:
            tool_kind= tool.tool_kind.value
            return tool_kind
        return None

    async def run_intractive(self):
        self.tui.print_welcome('Tiaga',lines=[
            f"model:{self.config.model_name} ",
            f"cwd:{self.config.cwd} ",
            f"command: /help /exit /config /appoval /model"
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
                    await self._process_message(user_input)
                except KeyboardInterrupt:
                    console.print(f"\n[dim] use /exit to quit[/dim]")
                except EOFError:
                    break           
            console.print(f"\n[dim]Goodbye[/dim]")
        


    async def run_single(self,message):
        async with Agent(self.config) as agent:
            self.agent = agent
            
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
                    event.data.get("output",""),
                    event.data.get("metadata",{}),
                    event.data.get("truncated","False")
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
        asyncio.run(cli.run_intractive())



if __name__ == "__main__":
    main()
