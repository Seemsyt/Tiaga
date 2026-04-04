from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from client.reaponse import TokenUsage

class AgentEventType(str, Enum):
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    AGENT_ERROR = "agent_error"

    TEXT_DELTA = "text_delta"      # ✅ swapped
    TEXT_COMPLETE = "text_complete" # ✅ swapped
@dataclass
class AgentEvent:
    type:AgentEventType
    data:dict[str,Any] = field(default_factory=dict)

    @classmethod
    def agent_start(cls,messages:str)->AgentEvent:
          return cls(
                type = AgentEventType.AGENT_START,
                data = {"message":messages},
          )
    
    @classmethod
    def agent_end(cls,usage:TokenUsage|None,response:str|None = None)->AgentEvent:
          return cls(
                type = AgentEventType.AGENT_END,
                data = {"response":response,"usage":usage.__dict__ if usage else None},
          )
    @classmethod
    def agent_error(cls,detail:str|None,error:str|None)->AgentEvent:
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
    
