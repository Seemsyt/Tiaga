"""LLM Provider abstraction layer - support for multiple LLM providers"""

from tiaga.client.providers.base import BaseLLMProvider, ProviderConfig
from tiaga.client.providers.capabilities import (
    ProviderCapabilities,
    detect_provider,
    detect_provider_from_model,
    detect_provider_from_url,
    get_provider_capabilities,
    PROVIDER_CAPABILITIES,
)
from tiaga.client.providers.provider_factory import (
    create_provider,
    get_provider_capabilities_info,
)
from tiaga.client.providers.openai_provider import OpenAIProvider

__all__ = [
    "BaseLLMProvider",
    "ProviderConfig",
    "ProviderCapabilities",
    "OpenAIProvider",
    "create_provider",
    "detect_provider",
    "detect_provider_from_model",
    "detect_provider_from_url",
    "get_provider_capabilities",
    "get_provider_capabilities_info",
    "PROVIDER_CAPABILITIES",
]
