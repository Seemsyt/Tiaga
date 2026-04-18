import logging
from typing import Any
from tiaga.config.config import Config
from tiaga.hooks.hook_system import HookSystem
from tiaga.safty.approval import ApprovalContext, ApprovalDecision, ApprovalManager
from tiaga.tools_manager.buildin import get_all_builtin_tool
from tiaga.tools_manager.base import Tool, ToolResult,ToolInvocation
from tiaga.tools_manager.subagent import SubagentTool, get_default_subagent_definition
from tiaga.tracing.trace import Trace

logger  = logging.getLogger(__name__)

class ToolRegistry:
    def __init__(self,config:Config):
        self._tools:dict[str,Tool] = {}
        self._mcp_tools:dict[str,Tool] = {}
        self.config = config


    @property
    def getmcp(self)->list[Tool]:
        tools = []
        for tool in self._mcp_tools.values():
            tools.append(tool)
        return tools
    


    def register(self,tool:Tool):
        if tool.name in self._tools :
            logger.warning(f"Overwriting existing tool{tool.name}")
        self._tools[tool.name] = tool
        logger.debug(f"register{tool.name}")

    def register_mcp(self,tool:Tool):

        self._mcp_tools[tool.name] = tool

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

        for tool in self._mcp_tools.values():
            tools.append(tool)
        if self.config.allowed_tools:
            allowed_tool = set(self.config.allowed_tools)
            tools = [t for t in tools if t.name in allowed_tool]
 

        return tools
    

    def get(self,name:str)->Tool:
        if name in self._tools:
            return self._tools.get(name)
        elif name in self._mcp_tools:
            return self._mcp_tools[name]
        

    def get_schemas(self): 
        return [tool.to_open_ai_schema() for tool in self.get_tools()]
    


    async def invoke(self,name:str,params:dict[str,Any],cwd,approval:ApprovalManager|None = None,hook_system:HookSystem|None = None,trace_system:Trace = None):
        tool = self.get(name)
        if tool is None:
            result = ToolResult.error_result(f"tool does not exists {name}")
            await hook_system.trigger_after_tool(name,params,result)
            return result
        validation_error =  tool.validate_params(params)
        if validation_error :
            result = ToolResult.error_result(f"Invalid parameters{validation_error}")
            await hook_system.trigger_after_tool(name,params,result)
            return result
        if trace_system:
            trace_system.trace_before_tool(name,params)
        await hook_system.trigger_before_tool(name,params)
        invocation  = ToolInvocation( params,
            cwd,)
        
        if approval:
            confirmation = await tool.get_confirmation(invocation)
            if confirmation:
                context = ApprovalContext(
                    tool_name=name,
                    params=params,
                    is_mutating=tool.is_mutating(params),
                    affected_paths=confirmation.affected_paths,
                    command=confirmation.command,
                    is_dangerous=confirmation.is_dangerous,
                )
                decision = await approval.check_approval(context=context)
                if decision == ApprovalDecision.REJECTED:
                    result =  ToolResult.error_result(
                        f"Opration was rejected by safer policy"
                    )
                    await hook_system.trigger_after_tool(name,params,result)
                    return result

                elif decision == ApprovalDecision.NEEDS_CONFIRMATION:
                    approved =  approval.request_confirmation(confirmation)
                    if not approved :
                        result= ToolResult.error_result(
                        f"Opration was rejected by safer policy"
                    )
                        await hook_system.trigger_after_tool(name,params,result)
                        return result

        try:
            result = await tool.execute(invocation)
            if trace_system:
                trace_system.trace_after_tool(name,params,result)
            await hook_system.trigger_after_tool(name,params,result)
            return result
        except Exception as e :
            logger.exception(f"Tool {name}raise an {e}")
            result =  ToolResult.error_result(
                f"internal error {str(e)} for {name}"
            )
            if trace_system:
                trace_system.trace_after_tool(name,params,result)
            await hook_system.trigger_after_tool(name,params,result)
            return result
def create_default_registry(config:Config) -> ToolRegistry:
    registry = ToolRegistry(config=config)
    for tool_cls in get_all_builtin_tool():
        registry.register(tool_cls(config))

    for sub_agent in get_default_subagent_definition():
        registry.register(SubagentTool(config,sub_agent))

    return registry



        
