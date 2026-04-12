

import asyncio

from tiaga.config.config import Config
from tiaga.tools_manager.mcp.client import MCPclient ,MCPServerStatus
from tiaga.tools_manager.mcp.mcp_tool import MCPTool
from tiaga.tools_manager.registry import ToolRegistry


class MCPManager:
    def __init__(self,config:Config):
        self.config = config
        self._clients:dict[str,MCPclient] = {}
        self.initialized = False


    async def initialize(self)->None:

        if self.initialized:
            return
        mcp_configs = self.config.mcp_servers


        if not mcp_configs:
            return
        for name ,server_config in mcp_configs.items():
            if not server_config.enabled:
                continue

            self._clients[name] = MCPclient(name=name,config=server_config,cwd=self.config.cwd)
        connect_task = [asyncio.wait_for(client.connect(),timeout=client.config.startup_timeout_seconds) for name , client in self._clients.items()]

        await asyncio.gather(*connect_task,return_exceptions=True)

        self.initialized = True


    def register_tools(self,registry:ToolRegistry)->int:

        count:int = 0 

        for client in self._clients.values():

            if client.status != MCPServerStatus.CONNECTED:
                continue

            for tool_info in client._tools.values():

                mcp = MCPTool(tool_info=tool_info,
                              client=client,
                              config = self.config,
                              name =f"mcp tool {tool_info.name}")
                registry.register_mcp(mcp)
                count +=1
        return count



    async def Shoutdown(self)->None:
        disconnection_task = [client.disconnect() for client in self._clients.values()]

        asyncio.gather(*disconnection_task,return_exceptions=True)

        self._clients.clear()

        self.initialized = False





