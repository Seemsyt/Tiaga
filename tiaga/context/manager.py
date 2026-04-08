
from typing import Any
from tiaga.config.config import Config
from tiaga.tools_manager.base import Tool

from .text import calculate_token

from .prompts import get_system_prompt
from dataclasses import dataclass, field

@dataclass
class MessageItem:
    role:str
    content:str|None
    tool_call_id:str|None = None
    tool_calls:list[dict[str,Any]] = field(default_factory=list)
    token_count:int|None = None



    def to_dict(self)->dict[str,Any]:
        result: dict[str,Any] = {"role":self.role}
        result["content"] = self.content if self.content is not None else ""

        if self.tool_call_id:
            result['tool_call_id'] = self.tool_call_id
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        return result

class ContextManager:
    def __init__(self, config: Config,memory:str|None,tools:list[Tool]|None):
        self.config = config
        self.system_prompt = get_system_prompt(config,memory,tools=tools)
        self.model_name = config.model_name or "qwen/qwen3.6-plus:free"
        self.messages:list[MessageItem] = []
    

        
        self.token_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    # --- Add message ---
    def add_user_message(self, content:str):
        item = MessageItem(
                role="user",
                content=content,
                token_count=calculate_token(
                    text=content,
                    model=self.model_name
                )
        )
        self.messages.append(item)

    def add_assistant_message(
        self,
        content:str|None,
        tool_calls:list[dict[str, Any]]|None = None,
    ):
        item = MessageItem(
                role="assistant",
                content=content or "",
                tool_calls=tool_calls or [],
                token_count=calculate_token(
                    text=content or "",
                    model=self.model_name
                )
        )
        self.messages.append(item)
    def add_tool_message(self,tool_id:str,tool_content:str):
        item = MessageItem(
            role="tool",
            content=tool_content or "",
            tool_call_id=tool_id,
            token_count=calculate_token(tool_content or "", self.model_name),
        )
        self.messages.append(item)


    # --- Get full context ---
    def get_messages(self):
        messages = []
        if self.system_prompt:
            messages.append({"role":"system","content":self.system_prompt})
        for item in self.messages:
            if isinstance(item, MessageItem):
                messages.append(item.to_dict())
            else:
                # Backward compatibility if older runs inserted raw dict items.
                messages.append(item)

        return messages

    # --- Update token usage ---
    def update_usage(self, usage: dict):
        self.token_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
        self.token_usage["completion_tokens"] += usage.get("completion_tokens", 0)
        self.token_usage["total_tokens"] += usage.get("total_tokens", 0)

    # --- Get usage ---
    def get_usage(self):
        return self.token_usage
