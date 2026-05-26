"""Google Gemini Provider Implementation"""

import json
from typing import Any, AsyncGenerator, Dict, List
import google.generativeai as genai

from tiaga.client.response import StreamEvent, StreamEventType, TextDelta, TokenUsage, ToolCall, ToolCallDelta, parse_tool_call_arguments
from tiaga.client.providers.base import BaseLLMProvider, ProviderConfig


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API provider"""

    async def initialize(self) -> None:
        """Initialize Gemini client"""
        genai.configure(api_key=self.config.api_key)
        self.model = genai.GenerativeModel(self.config.model_name)

    async def close(self) -> None:
        """Close the Gemini client"""
        # Gemini doesn't require explicit close
        self.model = None

    def build_tools(self, tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Convert tools to Gemini format
        
        Gemini uses Tool and ToolParameter from google.generativeai
        """
        gemini_tools = []
        
        for tool in tools:
            properties = tool.get("parameters", {}).get("properties", {})
            required = tool.get("parameters", {}).get("required", [])
            
            parameters = {
                "type": "object",
                "properties": properties,
                "required": required,
            }
            
            gemini_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": parameters,
                }
            })
        
        return gemini_tools

    def normalize_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize messages to Gemini format
        
        Gemini expects alternating user/model messages.
        System message is passed as system_instruction parameter.
        """
        normalized: List[Dict[str, Any]] = []
        
        for message in messages:
            role = message.get("role", "user")
            
            # Skip system messages - they go to system_instruction
            if role == "system":
                continue
            
            # Convert assistant -> model for Gemini
            if role == "assistant":
                role = "model"
            
            content = message.get("content", "")
            
            if isinstance(content, (dict, list)):
                safe_content = json.dumps(content)
            elif content is None:
                safe_content = ""
            else:
                safe_content = str(content)

            item: Dict[str, Any] = {
                "role": role,
                "parts": [{"text": safe_content}],
            }

            # Handle tool calls from assistant
            if role == "model" and message.get("tool_calls"):
                tool_calls_list = []
                for call in message.get("tool_calls", []):
                    function_obj = call.get("function", {})
                    args = function_obj.get("arguments", "")
                    if not isinstance(args, str):
                        args = json.dumps(args)

                    tool_calls_list.append({
                        "name": function_obj.get("name", ""),
                        "args": json.loads(args) if args else {},
                    })
                
                parts = [{"text": safe_content}]
                for tc in tool_calls_list:
                    parts.append({
                        "functionCall": {
                            "name": tc["name"],
                            "args": tc.get("args", {}),
                        }
                    })
                item["parts"] = parts

            # Handle tool responses
            if role == "user" and message.get("tool_call_id"):
                result = message.get("content", "")
                if isinstance(result, (dict, list)):
                    result = json.dumps(result)
                
                item["parts"] = [{
                    "functionResponse": {
                        "name": message.get("name", ""),
                        "response": {"result": result}
                    }
                }]

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
        """Execute chat completion with Gemini API"""
        if not self.model:
            await self.initialize()

        normalized_messages = self.normalize_messages(messages)
        system_message = self._extract_system_message(messages)
        
        generation_config = {
            "temperature": self.validate_temperature(self.config.temperature),
            "max_output_tokens": self.config.max_tokens or 8192,
        }

        # Build request kwargs
        kwargs: Dict[str, Any] = {
            "messages": normalized_messages,
            "generation_config": generation_config,
        }

        if system_message:
            kwargs["system_instruction"] = system_message

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
        """Handle streaming response from Gemini"""
        try:
            response = self.model.generate_content(
                **kwargs,
                stream=True,
            )
            
            finish_reason: str | None = None
            usage: TokenUsage | None = None
            
            for chunk in response:
                # Text content
                if chunk.text:
                    yield StreamEvent(
                        type=StreamEventType.TEXT_DELTA,
                        text_delta=TextDelta(content=chunk.text),
                    )
                
                # Tool calls
                if hasattr(chunk, 'function_calls'):
                    for fc in chunk.function_calls:
                        yield StreamEvent(
                            type=StreamEventType.TOOL_CALL_START,
                            tool_call_delta=ToolCallDelta(
                                call_id=getattr(fc, 'name', ''),
                                name=getattr(fc, 'name', ''),
                            ),
                        )
                        
                        args = getattr(fc, 'args', {})
                        if args:
                            yield StreamEvent(
                                type=StreamEventType.TOOL_CALL_DELTA,
                                tool_call_delta=ToolCallDelta(
                                    call_id=getattr(fc, 'name', ''),
                                    name=getattr(fc, 'name', ''),
                                    arguments_delta=json.dumps(args),
                                ),
                            )
                        
                        yield StreamEvent(
                            type=StreamEventType.TOOL_CALL_COMPLETE,
                            tool_call=ToolCall(
                                call_id=getattr(fc, 'name', ''),
                                name=getattr(fc, 'name', ''),
                                arguments=args or {},
                            ),
                        )
                
                if chunk.finish_reason:
                    finish_reason = str(chunk.finish_reason)
            
            # Get usage from prompt/completion token count
            if hasattr(response, 'usage_metadata'):
                usage_meta = response.usage_metadata
                usage = TokenUsage(
                    prompt_tokens=getattr(usage_meta, 'prompt_token_count', 0),
                    completion_tokens=getattr(usage_meta, 'candidates_token_count', 0),
                    total_tokens=getattr(usage_meta, 'total_token_count', 0),
                )
            
            yield StreamEvent(
                type=StreamEventType.MESSAGE_COMPLETE,
                finished_reason=finish_reason,
                usage=usage,
            )
        
        except Exception as e:
            yield StreamEvent(
                type=StreamEventType.ERROR,
                error=str(e),
            )

    async def _non_stream_response(
        self, kwargs: Dict[str, Any]
    ) -> StreamEvent:
        """Handle non-streaming response from Gemini"""
        try:
            response = self.model.generate_content(**kwargs)
            
            text_content = response.text if hasattr(response, 'text') else ""
            tool_calls: List[ToolCall] = []
            finish_reason = str(response.finish_reason) if hasattr(response, 'finish_reason') else "stop"
            
            # Extract tool calls
            if hasattr(response, 'function_calls'):
                for fc in response.function_calls:
                    tool_calls.append(ToolCall(
                        call_id=getattr(fc, 'name', ''),
                        name=getattr(fc, 'name', ''),
                        arguments=getattr(fc, 'args', {}),
                    ))
            
            # Extract usage
            usage = None
            if hasattr(response, 'usage_metadata'):
                usage_meta = response.usage_metadata
                usage = TokenUsage(
                    prompt_tokens=getattr(usage_meta, 'prompt_token_count', 0),
                    completion_tokens=getattr(usage_meta, 'candidates_token_count', 0),
                    total_tokens=getattr(usage_meta, 'total_token_count', 0),
                )
            
            return StreamEvent(
                type=StreamEventType.MESSAGE_COMPLETE,
                text_delta=TextDelta(text_content) if text_content else None,
                finished_reason=finish_reason,
                usage=usage,
            )
        
        except Exception as e:
            return StreamEvent(
                type=StreamEventType.ERROR,
                error=str(e),
            )

    def validate_temperature(self, temperature: float) -> float:
        """Validate temperature for Gemini (0.0 - 2.0)"""
        return max(0.0, min(2.0, temperature))

    def get_capabilities(self) -> Dict[str, Any]:
        """Get Gemini provider capabilities"""
        return {
            "supports_streaming": True,
            "supports_tool_calls": True,
            "supports_vision": True,
            "supports_parallel_tools": False,  # Gemini calls tools sequentially
            "max_tokens_per_request": 1000000,
        }
