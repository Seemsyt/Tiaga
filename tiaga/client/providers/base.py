"""Base LLM Provider abstraction - all providers implement this interface"""

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List
from dataclasses import dataclass
from tiaga.client.response import StreamEvent


@dataclass
class ProviderConfig:
    """Configuration for a provider"""
    api_key: str
    base_url: str | None = None
    model_name: str = ""
    temperature: float = 1.0
    max_tokens: int | None = None


class BaseLLMProvider(ABC):
    """Abstract base class for all LLM providers"""

    def __init__(self, config: ProviderConfig):
        self.config = config
        self.client = None

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the provider client"""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the provider client"""
        pass

    @abstractmethod
    def build_tools(self, tools: List[Dict[str, Any]]) -> Any:
        """Convert tools to provider-specific format
        
        Args:
            tools: List of tool definitions
            
        Returns:
            Provider-specific tool format
        """
        pass

    @abstractmethod
    def normalize_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize messages to provider-specific format
        
        Args:
            messages: Standard message format with role, content, etc.
            
        Returns:
            Provider-specific message format
        """
        pass

    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] | None = None,
        stream: bool = True,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Execute a chat completion request
        
        Args:
            messages: Normalized messages
            tools: Optional tools for this request
            stream: Whether to stream the response
            
        Yields:
            StreamEvent objects
        """
        pass

    def validate_temperature(self, temperature: float) -> float:
        """Validate and adjust temperature for this provider
        
        Returns:
            Valid temperature for this provider
        """
        # Override in subclasses with provider-specific validation
        return max(0.0, min(2.0, temperature))

    def validate_model_name(self, model_name: str) -> str:
        """Validate model name for this provider
        
        Returns:
            Valid model name
        """
        # Override in subclasses if needed
        return model_name

    @abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """Get provider capabilities
        
        Returns:
            Dictionary of capabilities (supporting tool_calls, vision, etc.)
        """
        pass
