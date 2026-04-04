from __future__ import annotations
from typing import AsyncGenerator
from client.llm_client import LLM_client
from client.reaponse import StreamEventType
from .events import AgentEvent,AgentEventType
from context.manager import ContextManager

class Agent:
    def __init__(self):
        self.client = LLM_client()
        self.usage = None
        self.context_manager = ContextManager()
    async def run(self,message:str):
        
        
        yield AgentEvent.agent_start(messages=message)
        self.context_manager.add_user_message(message)
        final_response = None
        async for event in self._agentic_loop():
            yield event
            if event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content","")
                

        yield AgentEvent.agent_end(usage=self.usage,response=final_response)
    async def _agentic_loop(self)->AsyncGenerator[AgentEvent]:
        response_text = ""
        async for event in self.client.chat_completion(message=self.context_manager.get_messages(),stream=True):
            if event.type == StreamEventType.TEXT_DELTA and event.text_delta:
                content = event.text_delta.content
                response_text = response_text + content
                yield AgentEvent.text_delta(content=content)

            elif event.type == StreamEventType.MESSAGE_COMPLETE:
                self.usage = event.usage  #
            elif event.type == StreamEventType.ERROR:
                yield AgentEvent.agent_error(
                detail=None,
                error=event.error or "Unknown error occurred."
                    )
        self.context_manager.add_assistant_message(response_text or"")
        if response_text:
            yield AgentEvent.text_complete(response_text)
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        if self.client:
            await self.client.close_client()
            self.client = None

