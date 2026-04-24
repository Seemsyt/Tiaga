import asyncio
import json
import logging
from typing import Any, AsyncGenerator

from dotenv import load_dotenv
from os import getenv

from tiaga.config.config import Config
from tiaga.client.providers import create_provider, ProviderConfig, get_provider_capabilities_info
from .response import StreamEvent, StreamEventType, TextDelta, TokenUsage, ToolCall, ToolCallDelta, parse_tool_call_arguments

load_dotenv()
logger = logging.getLogger(__name__)


class LLM_client:
    """Multi-LLM client supporting OpenAI, Anthropic, Gemini, and other providers"""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._provider = None
        self._capabilities = None

    async def initialize_provider(self) -> None:
        """Initialize the LLM provider"""
        try:
            provider_config = ProviderConfig(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                model_name=self.config.model_name,
                temperature=self.config.temperature,
            )
            
            self._provider = create_provider(provider_config)
            await self._provider.initialize()
            
            self._capabilities = get_provider_capabilities_info(
                self.config.model_name,
                self.config.base_url or ""
            )
            
            logger.info(f"LLM Provider initialized: {self._capabilities['provider']}")
        except Exception as e:
            logger.error(f"Failed to initialize LLM provider: {e}")
            raise

    def get_provider(self):
        """Get the current provider (lazy initialization)"""
        if self._provider is None:
            raise RuntimeError("Provider not initialized. Call initialize_provider() first.")
        return self._provider

    def has_capability(self, capability: str) -> bool:
        """Check if the current provider supports a capability"""
        if not self._capabilities:
            return False
        return self._capabilities.get(capability, False)

    async def close_client(self) -> None:
        """Close the provider client"""
        if self._provider:
            await self._provider.close()
            self._provider = None

    async def chat_completion(
        self,
        message: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Execute a chat completion with automatic provider selection
        
        Args:
            message: List of message dicts with role, content, etc.
            tools: Optional list of tool definitions
            stream: Whether to stream the response
            
        Yields:
            StreamEvent objects
        """
        # Lazy initialize provider on first use
        if self._provider is None:
            await self.initialize_provider()

        provider = self.get_provider()
        
        # Check if provider supports tool calling, warn if not available
        if tools and not self.has_capability("supports_tool_calls"):
            logger.warning(
                f"Tools requested but provider {self._capabilities['provider']} "
                f"does not support tool calling. Tools will be ignored."
            )
            tools = None

        # Use provider's chat completion
        async for event in provider.chat_completion(message, tools, stream):
            yield event

        
