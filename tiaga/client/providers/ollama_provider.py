from typing import Any, Dict

from tiaga.client.providers.openai_provider import OpenAIProvider


class OllamaProvider(OpenAIProvider):
    """Ollama provider - uses OpenAI-compatible API via Ollama's /v1 endpoint"""

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "supports_streaming": True,
            "supports_tool_calls": True,
            "supports_vision": False,
            "supports_parallel_tools": False,
        }
