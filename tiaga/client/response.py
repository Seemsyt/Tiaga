from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import json
from typing import Any
@dataclass
class TextDelta():
    content:str


class StreamEventType(str,Enum):
    TEXT_DELTA = "text_delta"
    MESSAGE_COMPLETE = 'message_complete'
    ERROR = 'error'

    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_DELTA='tool_call_delta'
    TOOL_CALL_COMPLETE = "tool_call_complete"

@dataclass
class TokenUsage:
    prompt_tokens :int = 0
    completion_tokens:int = 0
    total_tokens:int = 0
    cached_tokens:int = 0 

    def __add__(self,other:TokenUsage):
        return TokenUsage(prompt_tokens = self.prompt_tokens + other.prompt_tokens,
                completion_tokens=self.completion_tokens+other.completion_tokens,
                total_tokens=self.total_tokens+other.total_tokens,
                cached_tokens=self.cached_tokens+other.cached_tokens,
                )
@dataclass 
class ToolCallDelta:
    call_id:str 
    name:str|None = None
    arguments_delta:str|None = ""
@dataclass
class ToolCall:
    call_id:str 
    name:str|None = None
    arguments:str|None = ""

@dataclass
class StreamEvent:
    type:StreamEventType
    text_delta:TextDelta|None = None
    error:str|None=None
    finished_reason:str|None = None
    tool_call_delta:ToolCall|None = None
    tool_call: ToolCall | None = None  
    usage:TokenUsage|None = None
def parse_tool_call_arguments(args:str)->dict[str,Any]:
    if not args:
        return {}
    else:
        try:
            return json.loads(args)
        except json.JSONDecodeError as e:
            return {"raw_arguments":args}
@dataclass
class ToolResultMessage:
    tool_call_id :str
    content:str
    is_error:bool|None = None

    def to_open_ai_message(self)->dict[str,Any]:
        return {
            "role":"tool",
            "tool_call_id":self.tool_call_id,
            "content":self.content
        }
