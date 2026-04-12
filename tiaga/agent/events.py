from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from tiaga.client.response import TokenUsage
from tiaga.tools_manager.base import ToolResult

class AgentEventType(str, Enum):
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    AGENT_ERROR = "agent_error"

    TEXT_DELTA = "text_delta"      
    TEXT_COMPLETE = "text_complete" 

    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_END = "tool_call_end"
@dataclass
class AgentEvent:
    type:AgentEventType
    data:dict[str,Any] = field(default_factory=dict)

    @classmethod
    def agent_start(cls,messages:str)->AgentEventType:
          return cls(
                type = AgentEventType.AGENT_START,
                data = {"message":messages},
          )
    
    @classmethod
    def agent_end(cls,usage:TokenUsage|None=None,response:str|None = None)->AgentEventType:
          return cls(
                type = AgentEventType.AGENT_END,
                data = {"response":response,"usage":usage.__dict__ if usage else None},
          )
    @classmethod
    def agent_error(cls,detail:str|None,error:str|None)->AgentEventType:
          return cls(
                type = AgentEventType.AGENT_ERROR,
                data = {"error":error,"detail✌️":detail or {}}
          )
    @classmethod
    def text_delta(cls,content:str|None = None):
          return cls (
                type = AgentEventType.TEXT_DELTA,
                data = {"content":content or None}
          )
    @classmethod
    def text_complete(cls,content:str|None = None):
          return cls (
                type = AgentEventType.TEXT_COMPLETE,
                data = {"content":content or None}
          )
    @classmethod
    def tool_call_start(cls,call_id:str,name:str,arguments:dict[str,Any]):
         return cls(
              type = AgentEventType.TOOL_CALL_START,
              data={
                   "name":name,
                   "call_id":call_id,
                   "arguments":arguments,
              }
         )
    @classmethod
    def tool_call_complete(cls,call_id:str,name:str,result:ToolResult):
         return cls(
              type =  AgentEventType.TOOL_CALL_END,
              data={
                   "call_id":call_id,
                   "name":name,
                   "success":result.success,
                   "error":result.error,
                   "output":result.output,
                   "display_output": result.display_output if result.display_output is not None else result.output,
                   "metadata":result.metadata,
                   "diff":result.diff.create_diff() if result.diff else None,
                   "truncated":result.truncated,
                   "exit_code":result.exit_code,
              }
         )
         
