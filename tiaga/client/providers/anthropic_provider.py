"""Anthropic Claude Provider Implementation"""

import json
from typing import Any, AsyncGenerator, Dict, List
import anthropic

from tiaga.client.response import StreamEvent, StreamEventType, TextDelta, TokenUsage, ToolCall, ToolCallDelta, parse_tool_call_arguments
from tiaga.client.providers.base import BaseLLMProvider, ProviderConfig


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude API provider"""

    async def initialize(self) -> None:
        """Initialize Anthropic async client"""
        self.client = anthropic.AsyncAnthropic(
            api_key=self.config.api_key,
        )

    async def close(self) -> None:
        """Close the Anthropic client"""
        if self.client:
            await self.client.close()
            self.client = None

    def build_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert tools to Anthropic format
        
        Anthropic uses a different tool format:
        {
            "name": "tool_name",
            "description": "...",
            "input_schema": {
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }
        """
        anthropic_tools: List[Dict[str, Any]] = []
        for tool in tools:
            anthropic_tool = {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool.get("parameters", {
                    "type": "object",
                    "properties": {},
                }),
            }
            anthropic_tools.append(anthropic_tool)
        return anthropic_tools

    def normalize_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize messages to Anthropic format
        
        Anthropic doesn't support system role in messages array;
        system message should be passed separately as a parameter.
        """
        normalized: List[Dict[str, Any]] = []
        for message in messages:
            role = message.get("role", "user")
            
            # Skip system messages - they'll be passed to system parameter
            if role == "system":
                continue
                
            content = message.get("content", "")
            
            if isinstance(content, (dict, list)):
                safe_content = json.dumps(content)
            elif content is None:
                safe_content = ""
            else:
                safe_content = str(content)

            item: Dict[str, Any] = {
                "role": role,
                "content": safe_content,
            }

            # Handle tool calls
            if role == "assistant" and message.get("tool_calls"):
                tool_use_blocks: List[Dict[str, Any]] = []
                for call in message.get("tool_calls", []):
                    function_obj = call.get("function", {})
                    args = function_obj.get("arguments", "")
                    if not isinstance(args, str):
                        args = json.dumps(args)

                    tool_use_blocks.append({
                        "type": "tool_use",
                        "id": call.get("id", ""),
                        "name": function_obj.get("name", ""),
                        "input": json.loads(args) if args else {},
                    })
                
                if isinstance(item["content"], str):
                    item["content"] = [{
                        "type": "text",
                        "text": item["content"],
                    }]
                elif isinstance(item["content"], list):
                    item["content"] = [{
                        "type": "text",
                        "text": safe_content,
                    }]
                
                item["content"].extend(tool_use_blocks)

            normalized.append(item)
        
        return normalized

    def _extract_system_message(self, messages: List[Dict[str, Any]]) -> str:
        """Extract system message from messages list"""
        for message in messages:
            if message.get("role") == "system":
                content = message.get("content", "")
                if isinstance(content, (dict, list)):
                    return json.dumps(content)
                return str(content) if content else ""
        return ""

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] | None = None,
        stream: bool = True,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Execute chat completion with Anthropic API"""
        if not self.client:
            await self.initialize()

        normalized_messages = self.normalize_messages(messages)
        system_message = self._extract_system_message(messages)
        
        kwargs: Dict[str, Any] = {
            "model": self.config.model_name,
            "messages": normalized_messages,
            "max_tokens": self.config.max_tokens or 4096,
        }

        if system_message:
            kwargs["system"] = system_message

        if tools:
            kwargs["tools"] = self.build_tools(tools)

        # Retry logic
        for attempt in range(3):
            try:
                if stream:
                    async for event in self._stream_response(kwargs):
                        yield event
                else:
                    event = await self._non_stream_response(kwargs)
                    yield event
                return
            except Exception as e:
                if attempt < 2:
                    import asyncio
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
                else:
                    yield StreamEvent(
                        type=StreamEventType.ERROR,
                        error=str(e),
                    )
                    return

    async def _stream_response(
        self, kwargs: Dict[str, Any]
    ) -> AsyncGenerator[StreamEvent, None]:
        """Handle streaming response from Anthropic"""
        usage: TokenUsage | None = None
        stop_reason: str | None = None
        tool_calls: Dict[str, Dict[str, Any]] = {}

        with self.client.messages.stream(**kwargs) as stream:
            async for event in stream:
                # Handle different event types
                if hasattr(event, 'type'):
                    event_type = event.type
                    
                    # Text events
                    if event_type == 'content_block_delta':
                        if hasattr(event, 'delta'):
                            delta = event.delta
                            if hasattr(delta, 'type') and delta.type == 'text_delta':
                                if hasattr(delta, 'text'):
                                    yield StreamEvent(
                                        type=StreamEventType.TEXT_DELTA,
                                        text_delta=TextDelta(content=delta.text),
                                    )
                    
                    # Tool use events
                    elif event_type == 'content_block_start':
                        if hasattr(event, 'content_block'):
                            content_block = event.content_block
                            if hasattr(content_block, 'type') and content_block.type == 'tool_use':
                                tool_id = getattr(content_block, 'id', '')
                                tool_name = getattr(content_block, 'name', '')
                                tool_calls[tool_id] = {
                                    'id': tool_id,
                                    'name': tool_name,
                                    'input': '',
                                }
                                yield StreamEvent(
                                    type=StreamEventType.TOOL_CALL_START,
                                    tool_call_delta=ToolCallDelta(
                                        call_id=tool_id,
                                        name=tool_name,
                                    ),
                                )
                    
                    # Message completion
                    elif event_type == 'message_stop':
                        if hasattr(event, 'message'):
                            msg = event.message
                            if hasattr(msg, 'usage'):
                                usage = TokenUsage(
                                    prompt_tokens=msg.usage.input_tokens,
                                    completion_tokens=msg.usage.output_tokens,
                                    total_tokens=msg.usage.input_tokens + msg.usage.output_tokens,
                                )
                            if hasattr(msg, 'stop_reason'):
                                stop_reason = msg.stop_reason

        # Finalize tool calls
        for tool_id, tool_data in tool_calls.items():
            yield StreamEvent(
                type=StreamEventType.TOOL_CALL_COMPLETE,
                tool_call=ToolCall(
                    call_id=tool_data['id'],
                    name=tool_data['name'],
                    arguments=json.loads(tool_data['input']) if tool_data['input'] else {},
                ),
            )

        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            finished_reason=stop_reason,
            usage=usage,
        )

    async def _non_stream_response(
        self, kwargs: Dict[str, Any]
    ) -> StreamEvent:
        """Handle non-streaming response from Anthropic"""
        response = await self.client.messages.create(**kwargs)
        
        text_content = ""
        tool_calls: List[ToolCall] = []
        
        # Extract content
        for block in response.content:
            if hasattr(block, 'type'):
                if block.type == 'text' and hasattr(block, 'text'):
                    text_content = block.text
                elif block.type == 'tool_use':
                    tool_calls.append(ToolCall(
                        call_id=getattr(block, 'id', ''),
                        name=getattr(block, 'name', ''),
                        arguments=getattr(block, 'input', {}),
                    ))
        
        # Extract usage
        usage = None
        if hasattr(response, 'usage'):
            usage = TokenUsage(
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            )
        
        return StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            text_delta=TextDelta(text_content) if text_content else None,
            finished_reason=getattr(response, 'stop_reason', None),
            usage=usage,
        )

    def validate_temperature(self, temperature: float) -> float:
        """Validate temperature for Anthropic (0.0 - 1.0)"""
        return max(0.0, min(1.0, temperature))

    def get_capabilities(self) -> Dict[str, Any]:
        """Get Anthropic provider capabilities"""
        return {
            "supports_streaming": True,
            "supports_tool_calls": True,
            "supports_vision": True,
            "supports_parallel_tools": True,
            "max_tokens_per_request": 200000,
        }
