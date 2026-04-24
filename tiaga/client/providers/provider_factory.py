"""Provider Factory - creates the appropriate LLM provider"""

from typing import Any, Dict
import logging

from tiaga.client.providers.base import BaseLLMProvider, ProviderConfig
from tiaga.client.providers.capabilities import detect_provider, get_provider_capabilities
from tiaga.client.providers.ollama_provider import OllamaProvider
from tiaga.client.providers.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

# Map provider names to their classes - try to import optional providers
PROVIDER_CLASSES: Dict[str, type[BaseLLMProvider]] = {
    "openai": OpenAIProvider,
    "openrouter": OpenAIProvider,  # OpenRouter uses OpenAI-compatible API
    "ollama": OllamaProvider,  # Explicitly support Ollama
    "generic": OpenAIProvider,  # Default to OpenAI-compatible
}

# Try to import Anthropic provider
try:
    from tiaga.client.providers.anthropic_provider import AnthropicProvider
    PROVIDER_CLASSES["anthropic"] = AnthropicProvider
except ImportError:
    logger.debug("Anthropic provider not available (anthropic package not installed)")

# Try to import Gemini provider
try:
    from tiaga.client.providers.gemini_provider import GeminiProvider
    PROVIDER_CLASSES["gemini"] = GeminiProvider
except ImportError:
    logger.debug("Gemini provider not available (google-generativeai package not installed)")


def create_provider(config: ProviderConfig) -> BaseLLMProvider:
    """Create and return the appropriate LLM provider
    
    Args:
        config: Provider configuration
        
    Returns:
        Initialized provider instance
        
    Raises:
        ValueError: If provider is not supported
    """
    # Detect provider from model name and base_url
    detected_provider = detect_provider(config.model_name, config.base_url or "")
    
    logger.info(
        f"Creating provider for model '{config.model_name}' at '{config.base_url}' -> Detected: {detected_provider}"
    )
    
    # Get provider class
    provider_class = PROVIDER_CLASSES.get(detected_provider.lower())
    
    if not provider_class:
        # Fall back to OpenAI-compatible if not found
        logger.warning(
            f"Provider '{detected_provider}' not found, falling back to OpenAI-compatible"
        )
        provider_class = PROVIDER_CLASSES["generic"]
    
    # Create provider instance
    provider = provider_class(config)
    
    # Log capabilities
    capabilities = get_provider_capabilities(detected_provider)
    logger.info(
        f"Provider capabilities - Streaming: {capabilities.supports_streaming}, "
        f"Tools: {capabilities.supports_tool_calls}, Vision: {capabilities.supports_vision}"
    )
    
    return provider


def get_provider_capabilities_info(model_name: str, base_url: str = "") -> Dict[str, Any]:
    """Get capability information for a model/provider combination
    
    Args:
        model_name: Model name (e.g., "gpt-4", "claude-3", "minimax/minimax-m2.5:free")
        base_url: Base URL of the API endpoint
        
    Returns:
        Dictionary of capabilities
    """
    detected_provider = detect_provider(model_name, base_url)
    capabilities = get_provider_capabilities(detected_provider)
    
    return {
        "provider": detected_provider,
        "supports_streaming": capabilities.supports_streaming,
        "supports_tool_calls": capabilities.supports_tool_calls,
        "supports_vision": capabilities.supports_vision,
        "supports_parallel_tools": capabilities.supports_parallel_tools,
        "temperature_range": (capabilities.temperature_min, capabilities.temperature_max),
        "max_tokens": capabilities.max_tokens_per_request,
    }
