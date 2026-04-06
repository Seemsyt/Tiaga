import logging
from typing import Any
from tools_manager.buildin import get_all_builtin_tool
from tools_manager.base import Tool, ToolResult,ToolInvocation

logger  = logging.getLogger(__name__)

class ToolRegistry:
    def __init__(self):
        self._tools:dict[str,Tool] = {}
    def register(self,tool:Tool):
        if tool.name in self._tools :
            logger.warning(f"Overwriting existing tool{tool.name}")
        self._tools[tool.name] = tool
        logger.debug(f"register{tool.name}")

    def unregister(self,name):
        if name in self._tools:
            del self._tools[name]
            return True
        return False
    def get_tools(self):
        tools:list[Tool] = []
        for tool in self._tools.values():
            tools.append(tool)
        return tools
    def get(self,name:str)->Tool:
        if name in self._tools:
            return self._tools.get(name)
    def get_schemas(self): 
        return [tool.to_open_ai_schema() for tool in self.get_tools()]
    async def invoke(self,name:str,params:dict[str,Any],cwd):
        tool = self.get(name)
        if tool is None:
            return ToolResult.error_result(f"tool does not exists {name}")
        validation_error =  tool.validate_params(params)
        if validation_error :
            return ToolResult.error_result(f"Invalid parameters{validation_error}")
        invocation  = ToolInvocation( params,
            cwd,)
        try:
            result = await tool.execute(invocation)
            return result
        except Exception as e :
            logger.exception(f"Tool {name}raise an {e}")
            return {
                f"internal error{str(e)} for {name}"
                }
def create_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool_cls in get_all_builtin_tool():
        registry.register(tool_cls())

    return registry



        


