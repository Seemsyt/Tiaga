
from typing import Any
from tiaga.client.response import TokenUsage
from tiaga.config.config import Config
from tiaga.tools_manager.base import Tool
from datetime import datetime
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
    PRUNE_PROTECT_TOKEN = 40_000
    PRUNE_MINIMUM_TOKEN = 20_000


    def __init__(self, config: Config,memory:str|None,tools:list[Tool]|None):
        self.config = config
        self.system_prompt = get_system_prompt(config,memory,tools=tools)
        self.model_name = config.model_name or "qwen/qwen3.6-plus:free"
        self.messages:list[MessageItem] = []
        self._latest_usage:TokenUsage = TokenUsage()
        self._total_usage = TokenUsage()
        self.pruned_at:datetime|None = None
        
    

    @property
    def total_usage(self):
        return self._total_usage

    @total_usage.setter
    def total_usage(self,value):
        self._total_usage = value
    @property
    def len_msg(self):
        return len(self.messages)

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
        self._total_usage += usage
    # --- Get usage ---
    def get_usage(self):
        return self._total_usage
    
    def latest_usage(self,usage:dict):
        self._latest_usage = usage

    def need_compression(self)->bool:
        context_limit =  self.config.model.context_window
        token_usage = self._total_usage.total_tokens
        return token_usage > (context_limit*0.8)

    def repplace_with_summary(self,summary:str)->None:
        self.messages = []
        continuation_content = f"""# Context Restoration (Previous Session Compacted)

        The previous conversation was compacted due to context length limits. Below is a detailed summary of the work done so far. 

        **CRITICAL: Actions listed under "COMPLETED ACTIONS" are already done. DO NOT repeat them.**

        ---

        {summary}

        ---

        Resume work from where we left off. Focus ONLY on the remaining tasks."""

        summary_item = MessageItem(
            role="user",
            content=continuation_content,
            token_count=calculate_token(continuation_content,self.model_name)

        )
        
        self.messages.append(summary_item)

        ack_content = """I've reviewed the context from the previous session. I understand:
- The original goal and what was requested
- Which actions are ALREADY COMPLETED (I will NOT repeat these)
- The current state of the project
- What still needs to be done"""
        """I'll continue with the REMAINING tasks only, starting from where we left off."""
        ack_item = MessageItem(
            role="assistant",
            content=ack_content,
            token_count=calculate_token(ack_content, self.model_name),
        )
        self.messages.append(ack_item)

        continue_content = (
            "Continue with the REMAINING work only. Do NOT repeat any completed actions. "
            "Proceed with the next step as described in the context above."
        )

        continue_item = MessageItem(
            role="user",
            content=continue_content,
            token_count=calculate_token(continue_content, self.model_name),
        )
        self.messages.append(continue_item)

    def pruning_tool_outputs(self,)->int:
        user_message_count = sum(1 for msg in self.messages if msg.role == "user")


        total_token = 0 
        pruned_tokens = 0 
        to_prune :list[MessageItem] = []
        if user_message_count > 2:
            return 0
        for msg in reversed(self.messages):
            if msg.role == "tool" and msg.tool_call_id:
                if self.pruned_at:
                    break
                token_count = msg.token_count or calculate_token(msg.content,self.model_name) 
                total_token += token_count

                if total_token > self.PRUNE_PROTECT_TOKEN:
                    pruned_tokens += token_count
                    to_prune.append(msg)

        if pruned_tokens < self.PRUNE_MINIMUM_TOKEN:
            return 0
        pruned_count = 0 
        for msg in to_prune:
            msg.content = '[old tool result content cleared]'
            msg.token_count = calculate_token(msg.content,self.model_name)
            self.pruned_at = datetime.now()
            pruned_count +=1

        return pruned_count
    

    def clear(self)->None:
        self.messages = []

        




