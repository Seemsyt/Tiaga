from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
from typing import Any

from fastmcp.client import Client
from fastmcp.client.transports import SSETransport,StdioTransport
from tiaga.config.config import MCPServersConfig

class MCPServerStatus(str,Enum):
    DISCONNECTED = 'disconnected'
    CONNECTED = 'connected'
    CONNECTING = 'connecting'
    ERROR = 'error'

@dataclass
class MCPToolInfo:
    name:str
    description:str
    server_name:str = ""
    input_schema:dict[str,Any] = field(default_factory=dict)


class MCPclient:
    def __init__(self,name:str,config:MCPServersConfig,cwd:Path)->None:
        self.name = name 
        self.config = config 
        self.cwd = cwd
        self.status = MCPServerStatus.DISCONNECTED
        self.client:Client|None = None
        self._tools:dict[str,MCPToolInfo] = dict() 

    def _create_transport(self) -> SSETransport | StdioTransport:
        env = os.environ.copy()
        env.update(self.config.env)   # merge config overrides on top
        if self.config.command:
            return StdioTransport(
                command=self.config.command,
                args=list(self.config.args),
                env=env,              # ← pass merged env, not just self.config.env
                cwd=self.config.cwd or self.cwd,
                
            )
        else:
            return SSETransport(url=self.config.url)

    async def connect(self):
        if self.status == MCPServerStatus.CONNECTED:
            return 
        self.status = MCPServerStatus.CONNECTING
        try:
            self.client = Client(transport=self._create_transport())

            await self.client.__aenter__()

            tools_result  =  await self.client.list_tools()
            for tool in tools_result:
                self._tools[tool.name] = MCPToolInfo(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=(
                        tool.inputSchema if hasattr(tool, "inputSchema") else {}
                    ),
                    server_name=self.name,
                )
            self.status = MCPServerStatus.CONNECTED
        except Exception as e :
            self.status = MCPServerStatus.ERROR

            raise 

    async def disconnect(self)->None:
        if self.client:
            await self.client.__aexit__(None,None,None)
        self._tools.clear()
        self.status = MCPServerStatus.DISCONNECTED

    async def call_tool(self,tool_name:str,arguments:dict[str,Any]):

        if not self.client or self.status !=MCPServerStatus.CONNECTED:
            raise RuntimeError(f"Not connected to the server {self.name}")
        
        result = await self.client.call_tool(tool_name,arguments)


        output = []
        for item in result.content:
            if hasattr(item, "text"):
                output.append(item.text)
            else:
                output.append(str(item))

        return {
            "output": "\n".join(output),
            "is_error": result.is_error,
        }