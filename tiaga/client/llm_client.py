import asyncio
import json
from typing import Any,AsyncGenerator

from dotenv import load_dotenv

from tiaga.config.config import Config

from .response import StreamEvent, StreamEventType, TextDelta,TokenUsage, ToolCall, ToolCallDelta, parse_tool_call_arguments
load_dotenv()
from os import getenv
from openai import AsyncOpenAI, RateLimitError
class LLM_client:
    def __init__(self,config:Config)->None:
        self.client :AsyncOpenAI|None = None
        self._max_retries:int|None = 3
        self.config = config
       
    def get_client(self)->AsyncOpenAI:
        if self.client is None:
            
            self.client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            )
        return self.client
        
    async def close_client(self)->None:
        if self.client :
            await self.client.close()
            self.client = None
    def build_tool(self,tools:list[dict[str,Any]]):
        return [
            {
            "type":"function",
            "function":{
                "name": tool['name'],
                "description":tool.get("description",""),
                "parameters":tool.get("parameters",{"type":"object","properties":{}})
            }
            }for tool in tools
        ]
    def _normalize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")

            if isinstance(content, (dict, list)):
                safe_content = json.dumps(content)
            elif content is None:
                safe_content = ""
            else:
                safe_content = str(content)

            item: dict[str, Any] = {
                "role": role,
                "content": safe_content,
            }

            if role == "assistant" and message.get("tool_calls"):
                tool_calls: list[dict[str, Any]] = []
                for call in message.get("tool_calls", []):
                    function_obj = call.get("function", {})
                    args = function_obj.get("arguments", "")
                    if not isinstance(args, str):
                        args = json.dumps(args)

                    tool_calls.append(
                        {
                            "id": call.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": function_obj.get("name", ""),
                                "arguments": args,
                            },
                        }
                    )
                item["tool_calls"] = tool_calls

            if role == "tool" and message.get("tool_call_id"):
                item["tool_call_id"] = message["tool_call_id"]

            normalized.append(item)
        return normalized
    async def chat_completion(self,message:list[dict[str,Any]],tools:list[dict[str,Any]]|None= None,stream:bool = True)->AsyncGenerator[StreamEvent, None]:
        client = self.get_client()
        tools_calls:dict[int,dict[str,Any]] = {}
        normalized_messages = self._normalize_messages(message)
        kwargs = {
                    "model":self.config.model_name,
                    "messages":normalized_messages,
                    "stream":stream
                }
        if tools :
            kwargs['tools'] = self.build_tool(tools)
            kwargs['tool_choice'] = "auto"
        for attempt in range(self._max_retries+3):
            try:
                
                if stream:
                    async for chunk in self._stream_response(client,kwargs):
                        yield chunk
                else:
                    event =  await self._non_stream_response(client=client,kwargs=kwargs)
                    yield event
                return
            except Exception as e:
                if attempt < self._max_retries:
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)
                else:
                    yield StreamEvent(
                        type=StreamEventType.ERROR,
                        error=str(e)
                        )
                    return
    

    


    async def _stream_response(self, client: AsyncOpenAI, kwargs: dict[str, Any]) -> AsyncGenerator[StreamEvent, None]:
        response = await client.chat.completions.create(**kwargs)
        finish_reason: str | None = None
        usage: TokenUsage | None = None
        tool_calls: dict[int, dict[str, Any]] = {}

        async for chunk in response:
            if hasattr(chunk, 'usage') and chunk.usage:
                usage = TokenUsage(
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
                    cached_tokens=getattr(chunk.usage, "cached_tokens", None)
                )
            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            if choice.finish_reason:
                finish_reason = choice.finish_reason

            if delta.content:
                yield StreamEvent(
                type=StreamEventType.TEXT_DELTA,
                text_delta=TextDelta(content=delta.content),
            )

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index

                    if idx not in tool_calls:
                        tool_calls[idx] = {
                        "id": tc.id or "",
                        "name": tc.function.name or "" if tc.function else "",
                        "arguments": ""
                    }
                        if tc.function and tc.function.name:
                            yield StreamEvent(
                                type=StreamEventType.TOOL_CALL_START,
                            tool_call_delta=ToolCallDelta(
                                call_id=tool_calls[idx]['id'],
                                name=tc.function.name,
                            )
                        )

                    if tc.function and tc.function.arguments:
                        tool_calls[idx]["arguments"] += tc.function.arguments
                        yield StreamEvent(
                        type=StreamEventType.TOOL_CALL_DELTA,
                        tool_call_delta=ToolCallDelta(
                            call_id=tool_calls[idx]['id'],
                            name=tool_calls[idx]['name'],
                            arguments_delta=tc.function.arguments,
                        )
                    )

        for idx, tc in tool_calls.items():
            yield StreamEvent(
            type=StreamEventType.TOOL_CALL_COMPLETE,
            tool_call=ToolCall(
                call_id=tc["id"],
                name=tc["name"],
                arguments=json.loads(tc["arguments"]),
            )
        )

        yield StreamEvent(
        type=StreamEventType.MESSAGE_COMPLETE,
        finished_reason=finish_reason,
        usage=usage,
    )
        



    async def _non_stream_response(self,client:AsyncOpenAI,kwargs:dict[str,Any])->StreamEvent:
        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message
        text_delta = None
        usage = None
        if message.content:
            text_delta = TextDelta(message.content)
        tool_calls: list[ToolCall] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        call_id=tc.id,
                        name=tc.function.name,
                        arguments=parse_tool_call_arguments(tc.function.arguments),
                    )
                )
        if response.usage:
            usage = TokenUsage(prompt_tokens=response.usage.prompt_tokens,
                               completion_tokens=response.usage.completion_tokens,
                               total_tokens=response.usage.total_tokens,
                               cached_tokens = getattr(response.usage, "cached_tokens", None))
        return StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            text_delta=text_delta,
            finished_reason=choice.finish_reason,
            usage=usage,

        )





        
