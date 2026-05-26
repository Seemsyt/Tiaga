"""Provider capabilities matrix - defines what each LLM provider supports"""

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class ProviderCapabilities:
    """Defines what features a provider supports"""
    supports_streaming: bool = True
    supports_tool_calls: bool = False
    supports_vision: bool = False
    supports_parallel_tools: bool = False
    supports_cached_tokens: bool = False
    max_tokens_per_request: int = 4096
    temperature_min: float = 0.0
    temperature_max: float = 2.0
    custom_parameters: Dict[str, Any] = None

    def __post_init__(self):
        if self.custom_parameters is None:
            self.custom_parameters = {}


# Provider capabilities matrix
PROVIDER_CAPABILITIES: Dict[str, ProviderCapabilities] = {
    # OpenAI Models
    "openai": ProviderCapabilities(
        supports_streaming=True,
        supports_tool_calls=True,
        supports_vision=True,
        supports_parallel_tools=True,
        supports_cached_tokens=True,
        max_tokens_per_request=128000,
        temperature_min=0.0,
        temperature_max=2.0,
    ),
    # Anthropic Claude
    "anthropic": ProviderCapabilities(
        supports_streaming=True,
        supports_tool_calls=True,
        supports_vision=True,
        supports_parallel_tools=True,
        supports_cached_tokens=False,
        max_tokens_per_request=200000,
        temperature_min=0.0,
        temperature_max=1.0,
    ),
    # Google Gemini
    "gemini": ProviderCapabilities(
        supports_streaming=True,
        supports_tool_calls=True,
        supports_vision=True,
        supports_parallel_tools=False,
        supports_cached_tokens=False,
        max_tokens_per_request=1000000,
        temperature_min=0.0,
        temperature_max=2.0,
    ),
    # OpenRouter (OpenAI-compatible wrapper)
    "openrouter": ProviderCapabilities(
        supports_streaming=True,
        supports_tool_calls=True,
        supports_vision=False,
        supports_parallel_tools=False,
        supports_cached_tokens=False,
        max_tokens_per_request=200000,
        temperature_min=0.0,
        temperature_max=2.0,
    ),
    # Ollama (local, OpenAI-compatible)
    "ollama": ProviderCapabilities(
        supports_streaming=True,
        supports_tool_calls=False,  # Depends on model
        supports_vision=False,
        supports_parallel_tools=False,
        supports_cached_tokens=False,
        max_tokens_per_request=32768,
        temperature_min=0.0,
        temperature_max=2.0,
    ),
    # Cohere
    "cohere": ProviderCapabilities(
        supports_streaming=False,
        supports_tool_calls=True,
        supports_vision=False,
        supports_parallel_tools=False,
        supports_cached_tokens=False,
        max_tokens_per_request=4096,
        temperature_min=0.0,
        temperature_max=2.0,
    ),
    # Groq (fast inference)
    "groq": ProviderCapabilities(
        supports_streaming=True,
        supports_tool_calls=True,
        supports_vision=False,
        supports_parallel_tools=False,
        supports_cached_tokens=False,
        max_tokens_per_request=4096,
        temperature_min=0.0,
        temperature_max=2.0,
    ),
    # Mistral
    "mistral": ProviderCapabilities(
        supports_streaming=True,
        supports_tool_calls=True,
        supports_vision=False,
        supports_parallel_tools=False,
        supports_cached_tokens=False,
        max_tokens_per_request=32768,
        temperature_min=0.0,
        temperature_max=1.0,
    ),
    # Generic OpenAI-compatible
    "generic": ProviderCapabilities(
        supports_streaming=True,
        supports_tool_calls=True,
        supports_vision=False,
        supports_parallel_tools=False,
        supports_cached_tokens=False,
        max_tokens_per_request=4096,
        temperature_min=0.0,
        temperature_max=2.0,
    ),
}


def get_provider_capabilities(provider_name: str) -> ProviderCapabilities:
    """Get capabilities for a provider, default to generic if not found"""
    return PROVIDER_CAPABILITIES.get(provider_name.lower(), PROVIDER_CAPABILITIES["generic"])


def detect_provider_from_url(base_url: str) -> str:
    """Detect provider from base_url"""
    url_lower = base_url.lower()
    if "openai" in url_lower:
        return "openai"
    elif "anthropic" in url_lower:
        return "anthropic"
    elif "gemini" in url_lower or "google" in url_lower:
        return "gemini"
    elif "openrouter" in url_lower:
        return "openrouter"
    elif "ollama" in url_lower or "localhost" in url_lower or "127.0.0.1" in url_lower:
        return "ollama"
    elif "cohere" in url_lower:
        return "cohere"
    elif "groq" in url_lower:
        return "groq"
    elif "mistral" in url_lower:
        return "mistral"
    return "generic"


def detect_provider_from_model(model_name: str) -> str:
    """Detect provider from model name"""
    model_lower = model_name.lower()
    
    if model_lower.startswith("gpt-") or model_lower.startswith("gpt4"):
        return "openai"
    elif "claude" in model_lower:
        return "anthropic"
    elif "gemini" in model_lower:
        return "gemini"
    elif "/" in model_lower:
        provider = model_lower.split("/")[0]
        if provider in PROVIDER_CAPABILITIES:
            return provider
        return "openrouter"  # Assume OpenRouter format
    elif "ollama" in model_lower or model_lower.startswith("llama"):
        return "ollama"
    elif "cohere" in model_lower:
        return "cohere"
    elif "groq" in model_lower:
        return "groq"
    elif "mistral" in model_lower:
        return "mistral"
    
    return "generic"


def detect_provider(model_name: str, base_url: str) -> str:
    """Detect provider from model name and/or base_url"""
    # First try to detect from model name
    provider_from_model = detect_provider_from_model(model_name)
    if provider_from_model != "generic":
        return provider_from_model
    
    # Then try to detect from URL
    return detect_provider_from_url(base_url)
