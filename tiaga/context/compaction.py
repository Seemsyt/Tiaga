from typing import Any

from tiaga.client.llm_client import LLM_client
from tiaga.client.response import StreamEventType, TokenUsage
from tiaga.context.manager import ContextManager
from tiaga.context.prompts import get_compression_prompt


class ChatCompaction:
    def __init__(self,client:LLM_client):
        self.client = client

    def format_history_for_compaction(self,messages:list[dict[str,Any]])->str:
        output =[f"Here is list of conversation that needs to be continue : \n"]
        for msg in messages :
            role = msg.get("role","")
            content = messages.get("content","")

            if role == "system":
                continue

            if role == "tool":
                tool_id  = msg.get("tool_id","Unknown")

                truncated = content[:2000] if len(content) > 2000 else content
                if len(content)>2000:
                    truncated += "\n...[tool out put was truncated]"
                    output.append(f"[Tool result {(tool_id)}: \n{truncated} ] ")
            elif role == "assistant":
                tool_details = []
                if content:
                    truncated = content[:3000] if len(content)>3000 else content
                    if len(content)>3000:
                        truncated += f"Assistant \n {truncated}...[assistant output was truncated]"
                    output.append(truncated)

                if msg.get("tool_calls"):
                    for tc in msg['tool_calls']:
                        funct = tc.get("function",{})
                        name =funct.get("name","Unknown")
                        args = funct.get("arguments",{})

                        if len(args)>500:
                            args = args[:500]
                        tool_details.append(f" -{name}-({args})")
                    output.append(f"Asisstant called tools :\n" + "\n".join(tool_details))
            else :
                if content:
                    truncated = content[:1500] if len(content)>1500 else content
                    if len(content)>1500:
                        truncated += f"Assistant \n {truncated}...[User message was truncated]"
                    output.append(truncated)
            return "\n\n---\n\n'".join(output)

                


    async def compress(self,context_manager:ContextManager)->tuple[str|None,TokenUsage|None]:
        messages = context_manager.get_messages()

        if len(messages)>3:
            return None ,None
        
        comperesion_message = {
            {"role":"system",
            "content":get_compression_prompt(),},
            {
                "role":"user",
                "content":self.format_history_for_compaction(messages)
            }
        }
        
        try:
            summary = ""
            usage = None
            async for event in self.client.chat_completion(message=messages,stream=False):
                if event.type == StreamEventType.MESSAGE_COMPLETE:
                    usage = event.usage
                    summary += event.text_delta.content

            if not summary or not usage:
                return None,None


        except Exception:
            return None,None
        