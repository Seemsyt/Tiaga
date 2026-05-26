from typing import Any

from tiaga.client.llm_client import LLM_client
from tiaga.client.response import StreamEventType, TokenUsage
from tiaga.context.manager import ContextManager
from tiaga.context.prompts import get_compression_prompt


class ChatCompaction:
    def __init__(self,client:LLM_client):
        self.client = client

    def format_history_for_compaction(self,messages:list[dict[str,Any]])->str:
        output = ["Here is the conversation history that needs to be compacted:"]
        for msg in messages:
            role = msg.get("role", "")
            content = str(msg.get("content", "") or "")

            if role == "system":
                continue

            if role == "tool":
                tool_id = msg.get("tool_call_id", "Unknown")
                truncated = content[:2000] if len(content) > 2000 else content
                if len(content) > 2000:
                    truncated += "\n...[tool output was truncated]"
                output.append(f"[TOOL {tool_id}]\n{truncated}")
            elif role == "assistant":
                truncated = content[:3000] if len(content) > 3000 else content
                if len(content) > 3000:
                    truncated += "\n...[assistant output was truncated]"
                if truncated:
                    output.append(f"[ASSISTANT]\n{truncated}")

                tool_details = []
                for tc in msg.get("tool_calls", []):
                    function_obj = tc.get("function", {})
                    name = function_obj.get("name", "Unknown")
                    args = str(function_obj.get("arguments", ""))
                    if len(args) > 500:
                        args = args[:500] + "...[truncated]"
                    tool_details.append(f"- {name}({args})")
                if tool_details:
                    output.append("Assistant called tools:\n" + "\n".join(tool_details))
            else:
                truncated = content[:1500] if len(content) > 1500 else content
                if len(content) > 1500:
                    truncated += "\n...[user message was truncated]"
                if truncated:
                    output.append(f"[USER]\n{truncated}")

        return "\n\n---\n\n".join(output)

                


    async def compress(self,context_manager:ContextManager)->tuple[str|None,TokenUsage|None]:
        messages = context_manager.get_messages()

        # Skip compaction when there is too little conversation history to compress.
        if len(messages) <= 3:
            return None, None
        
        compression_message = [
            {
                "role": "system",
                "content": get_compression_prompt(),
            },
            {
                "role": "user",
                "content": self.format_history_for_compaction(messages),
            },
        ]
        
        try:
            summary = ""
            usage: TokenUsage | None = None
            async for event in self.client.chat_completion(message=compression_message, stream=False):
                if event.type == StreamEventType.MESSAGE_COMPLETE:
                    usage = event.usage
                    if event.text_delta and event.text_delta.content:
                        summary += event.text_delta.content

            if not summary :
                return None, None

            return summary, usage

        except Exception:
            return None, None
        
