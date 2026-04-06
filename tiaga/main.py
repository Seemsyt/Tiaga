import sys
from typing import Any
from ui.render import TUI,_get_console
import click
import asyncio
from client.llm_client import LLM_client
from agent.agent import Agent,AgentEventType
console = _get_console()



class CLI():
    def __init__(self):
        self.agent:Agent|None = None
        self.tui = TUI(console=console)
        self.assistant_streaming = False

    def get_tool_kind(self,tool_name):
        tool= self.agent.tool_registry.get(tool_name)
        tool_kind= tool.tool_kind.value
        return tool_kind

    async def run_single(self,message):
        async with Agent() as agent:
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
                self.tui.render_tool_call_start(event.data.get('call_id',""),tool_name,tool_kind,event.data.get("arguments",{}))
            

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
def main(prompt:str|None = None):

    cli = CLI()
    # messagges = [
    #     {"role":"user","content":prompt},

    # ]
    if prompt:
        result = asyncio.run(cli.run_single(prompt))
        if result is None:
            raise sys.exit(1)


if __name__ == "__main__":
    main()

