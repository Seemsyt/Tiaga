
from typing import Any

from .text import calculate_token

# from .prompts import get_system_prompt
from dataclasses import dataclass

@dataclass
class MessageItem:
    role:str
    content:str
    token_count:int|None = None
    def to_dict(self)->dict[str,Any]:
        result: dict[str,Any] = {"role":self.role}
        if self.content :
            result["content"] = self.content
        return result

class ContextManager:
    def __init__(self):
        self.system_prompt = None#get_system_prompt()
        self.model_name = "qwen/qwen3.6-plus:free"
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

    def add_assistant_message(self, content:str):
        item = MessageItem(
                role="assistant",
                content=content or "",
                token_count=calculate_token(
                    text=content,
                    model=self.model_name
                )
        )
        self.messages.append(item)

    # --- Get full context ---
    def get_messages(self):
        messages = []
        if self.system_prompt:
            messages.append({"role":"system","content":self.system_prompt})
        for item in self.messages:
            messages.append(item.to_dict())

        return messages

    # --- Update token usage ---
    def update_usage(self, usage: dict):
        self.token_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
        self.token_usage["completion_tokens"] += usage.get("completion_tokens", 0)
        self.token_usage["total_tokens"] += usage.get("total_tokens", 0)

    # --- Get usage ---
    def get_usage(self):
        return self.token_usage

