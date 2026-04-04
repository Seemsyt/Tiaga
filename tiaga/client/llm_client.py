import asyncio
from typing import Any,AsyncGenerator

from dotenv import load_dotenv

from .reaponse import StreamEvent, StreamEventType, TextDelta,TokenUsage
load_dotenv()
from os import getenv
from openai import AsyncOpenAI, RateLimitError
class LLM_client:
    def __init__(self)->None:
        self.client :AsyncOpenAI|None = None
        self._max_retries:int|None = 3
       
    def get_client(self)->AsyncOpenAI:
        if self.client is None:
           
            self.client = AsyncOpenAI(
            api_key=getenv("OPEN_ROUTER_API_KEY"),
            base_url=getenv("BASE_URL"),
            )
        return self.client
        
    async def close_client(self)->None:
        if self.client :
            await self.client.close()
            self.client = None
            
    async def chat_completion(self,message:dict[str,Any],stream:bool = True)->AsyncGenerator[StreamEvent]:
        client = self.get_client()
        kwargs = {
                    "model":"qwen/qwen3.6-plus:free",
                    "messages":message,
                    "stream":stream
                }
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
    

    


    async def _stream_response(self,client:AsyncOpenAI,kwargs:dict[str,Any])->AsyncGenerator[StreamEvent]:
        response = None
        usage = None
        response = await client.chat.completions.create(**kwargs)
        async for chunk in response:
                if hasattr(chunk,'usage') and chunk.usage:
                    usage = TokenUsage(prompt_tokens=chunk.usage.prompt_tokens,
                               completion_tokens=chunk.usage.completion_tokens,
                               total_tokens=chunk.usage.total_tokens,
                               cached_tokens = getattr(chunk.usage, "cached_tokens", None))
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





        