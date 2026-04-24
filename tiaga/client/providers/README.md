# Multi-LLM Provider System

This directory contains the provider abstraction layer that enables **Tiaga** to work with any LLM provider.

---

## 🚀 Quick Start Guide for New Users

### Step 1: Install Tiaga

```bash
# Clone the repository
git clone https://github.com/yourusername/tiaga.git
cd tiaga

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .
```

### Step 2: Get an API Key

Choose your preferred LLM provider:

#### Option A: OpenAI (Recommended for beginners)
1. Go to https://platform.openai.com/api-keys
2. Create a new API key
3. Copy the key (starts with `sk-`)

#### Option B: OpenRouter (Best for cost)
1. Go to https://openrouter.ai
2. Create account and get API key
3. Supports 100+ models (including minimax, llama, etc.)

#### Option C: Ollama (Local, no API key needed)
1. Download from https://ollama.ai
2. Run: `ollama run llama2` (or any model)
3. Ollama runs on `http://localhost:11434`

#### Option D: Groq (Fast & free)
1. Go to https://console.groq.com
2. Create account and get API key
3. Free tier supports several models

### Step 3: Configure Your Provider

Edit your Tiaga configuration file (typically `~/.tiaga/config.toml` or set via commands):

#### For OpenAI:
```toml
[model]
name = "gpt-4"
provider = "openai"
api_key = "sk-your-api-key-here"
base_url = "https://api.openai.com/v1"
temperature = 0.7
```

#### For OpenRouter (example with minimax):
```toml
[model]
name = "minimax/minimax-m2.5:free"
provider = "openrouter"
api_key = "sk-or-v1-your-openrouter-key"
base_url = "https://openrouter.ai/api/v1"
temperature = 0.7
```

#### For Ollama (local):
```toml
[model]
name = "llama2"
provider = "ollama"
base_url = "http://localhost:11434/v1"
temperature = 0.7
```

#### For Groq:
```toml
[model]
name = "mixtral-8x7b-32768"
provider = "groq"
api_key = "gsk-your-groq-key"
base_url = "https://api.groq.com/openai/v1"
temperature = 0.7
```

### Step 4: Change Settings in Tiaga CLI

Once Tiaga is running, you can dynamically update your configuration:

```bash
# Set or change the model
/model gpt-4
# or for OpenRouter
/model minimax/minimax-m2.5:free

# Update API key
/api_key sk-or-v1-your-new-key

# Update base URL
/base_url https://api.openai.com/v1

# See current settings
/help
```

**Note**: Settings are automatically saved to your config file and reload immediately.

### Step 5: Run Your First Chat

```bash
# Start Tiaga
python -m tiaga.main

# Or if you have a different entry point
tiaga

# Type your first message and hit Enter
You: What is machine learning?

# Tiaga will respond using your configured LLM
```

### Step 6: Verify Your Setup

Check if everything is working:

```python
# Open Python REPL
python

# Run this code:
from tiaga.client.providers import get_provider_capabilities_info

info = get_provider_capabilities_info("gpt-4", "https://api.openai.com/v1")
print(f"Provider: {info['provider']}")
print(f"Tools supported: {info['supports_tool_calls']}")
print(f"Vision supported: {info['supports_vision']}")
print(f"Max tokens: {info['max_tokens_per_request']}")

# You should see: Provider: openai (or your provider name)
```

---

## ✨ Supported Providers (At a Glance)

| Provider | Cost | Setup Time | Features | Best For |
|----------|------|------------|----------|----------|
| **OpenAI** | Paid | 2 min | Full (tools, vision) | Production, best quality |
| **OpenRouter** | Cheap | 2 min | Full | Budget-conscious, variety |
| **Groq** | Free tier | 2 min | Tools, streaming | Speed, free trials |
| **Ollama** | Free | 10 min | Streaming | Privacy, learning |
| **Mistral** | Paid | 2 min | Tools, streaming | French LLMs |
| **Anthropic** | Paid | 2 min | Tools, vision | Claude models |

---

## Architecture

```
LLM_client (entry point)
    ↓
    ├→ Provider detection (auto from model name or URL)
    ├→ Factory pattern (creates right provider)
    └→ Provider interface (all implement BaseLLMProvider)
        ├→ OpenAIProvider (OpenAI, OpenRouter, Ollama, etc.)
        ├→ AnthropicProvider (Claude - not yet implemented)
        ├→ GeminiProvider (Google Gemini - not yet implemented)
        └→ CohereProvider (Cohere - not yet implemented)
```

## Files

- **`capabilities.py`** - Provider capability matrix and auto-detection
- **`base.py`** - Abstract provider interface
- **`openai_provider.py`** - OpenAI and OpenAI-compatible provider
- **`provider_factory.py`** - Factory that creates the right provider
- **`__init__.py`** - Public API exports

## Supported Providers

### ✅ Fully Implemented

| Provider | Model Examples | Features |
|----------|---|---|
| **OpenAI** | gpt-4, gpt-3.5-turbo | Streaming, Tools, Vision |
| **OpenRouter** | minimax/minimax-m2.5:free | Streaming, Tools via wrapper |
| **Groq** | mixtral-8x7b-32768 | Fast streaming, Tools |
| **Mistral** | mistral-large | Streaming, Tools |
| **Ollama** | llama2, neural-chat | Streaming (text only, no tools) |
| **Generic OpenAI-Compat** | Any OpenAI-like API | Streaming, Tools |

### ⏳ Partially Supported (Stubs)

| Provider | Status | Notes |
|----------|--------|-------|
| **Anthropic** | Detected, falls back | Custom tool format needed |
| **Google Gemini** | Detected, falls back | Different client & format |
| **Cohere** | Detected, falls back | No streaming by default |

## Usage

### Basic Usage (Auto-Detection)

```python
from tiaga.client.llm_client import LLM_client
from tiaga.config.config import Config

# Create config with your model
config = Config()
config.model.name = "minimax/minimax-m2.5:free"
config.base_url_value = "https://openrouter.ai/api/v1"
config.api_key_value = "sk-or-v1-..."

# Create client (auto-detects provider)
client = LLM_client(config)

# Use it
async for event in client.chat_completion(messages, tools, stream=True):
    print(event)
```

### Check Capabilities

```python
from tiaga.client.providers import get_provider_capabilities_info

info = get_provider_capabilities_info(
    "minimax/minimax-m2.5:free",
    "https://openrouter.ai/api/v1"
)

print(f"Provider: {info['provider']}")
print(f"Tools supported: {info['supports_tool_calls']}")
print(f"Vision supported: {info['supports_vision']}")
```

### Manual Provider Creation

```python
from tiaga.client.providers import create_provider, ProviderConfig

config = ProviderConfig(
    api_key="sk-...",
    base_url="https://api.openai.com/v1",
    model_name="gpt-4",
    temperature=0.7
)

provider = create_provider(config)
await provider.initialize()

# Use provider
async for event in provider.chat_completion(messages, tools, stream=True):
    print(event)
```

## Adding a New Provider

### 1. Create Provider File

Create `tiaga/client/providers/anthropic_provider.py`:

```python
from tiaga.client.providers.base import BaseLLMProvider, ProviderConfig
from tiaga.client.response import StreamEvent
from typing import Any, AsyncGenerator, Dict, List
import anthropic

class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider"""
    
    async def initialize(self) -> None:
        self.client = anthropic.AsyncAnthropic(api_key=self.config.api_key)
    
    async def close(self) -> None:
        if self.client:
            await self.client.close()
    
    def build_tools(self, tools: List[Dict[str, Any]]) -> List[Dict]:
        # Convert to Anthropic format
        return [
            {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool.get("parameters", {})
            }
            for tool in tools
        ]
    
    def normalize_messages(self, messages: List[Dict]) -> List[Dict]:
        # Convert to Anthropic format
        # (Anthropic has different message structure)
        pass
    
    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] | None = None,
        stream: bool = True,
    ) -> AsyncGenerator[StreamEvent, None]:
        # Implementation using self.client.messages.create()
        pass
    
    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "supports_streaming": True,
            "supports_tool_calls": True,
            "supports_vision": True,
            "supports_parallel_tools": True,
        }
```

### 2. Register in Factory

In `provider_factory.py`:

```python
from tiaga.client.providers.anthropic_provider import AnthropicProvider

PROVIDER_CLASSES = {
    ...
    "anthropic": AnthropicProvider,
    ...
}
```

### 3. That's It!

Auto-detection and factory will handle everything:

```python
model = "claude-3-opus-20240229"
# Automatically → AnthropicProvider
```

## Provider Detection Algorithm

1. **Model name priority**: "gpt-4" → OpenAI, "claude-3" → Anthropic
2. **URL fallback**: "openai.com" → OpenAI, "anthropic.com" → Anthropic
3. **Format detection**: "provider/model" → Look for provider in PROVIDER_CAPABILITIES
4. **Localhost**: "localhost" or "127.0.0.1" → Ollama
5. **Default**: Generic OpenAI-compatible

## Capability Matrix

Each provider defines what it supports:

```python
@dataclass
class ProviderCapabilities:
    supports_streaming: bool = True          # Can stream responses?
    supports_tool_calls: bool = True         # Can call functions?
    supports_vision: bool = False            # Can see images?
    supports_parallel_tools: bool = True     # Can call multiple tools at once?
    supports_cached_tokens: bool = False     # Supports token caching?
    max_tokens_per_request: int = 4096       # Max context window
    temperature_min: float = 0.0
    temperature_max: float = 2.0
```

## Error Handling

### Tools Not Supported

If tools are requested on a provider that doesn't support them:

```python
# In llm_client.py
if tools and not self.has_capability("supports_tool_calls"):
    logger.warning(f"Tools not supported, ignoring...")
    tools = None  # Conversation continues without tools
```

### Provider Not Yet Implemented

Falls back to OpenAI-compatible:

```python
# Unknown provider → tries OpenAI-compatible
provider = create_provider(config)
# If provider not found, uses OpenAIProvider as fallback
```

## Testing Providers

```bash
# Run provider tests
python -m pytest tiaga/client/providers/

# Or manually test
python -c "
from tiaga.client.providers import get_provider_capabilities_info
info = get_provider_capabilities_info('gpt-4', 'https://api.openai.com/v1')
print(info)
"
```

## Common Issues & Troubleshooting

### 🔴 "Authentication failed" or "Invalid API key"

**Cause**: API key is invalid, expired, or not set

**Solutions**:
1. Double-check your API key (copy-paste carefully, no extra spaces)
2. Make sure the API key hasn't expired
3. Verify key permissions in provider dashboard
4. Check provider is using the right URL (base_url)

```bash
# In Tiaga:
/api_key sk-your-new-key  # Update key and reconnect
```

### 🔴 "Provider 'xyz' not found, falling back to OpenAI-compatible"

**Cause**: Provider needs to be fully implemented

**Solution**: 
- Use a supported provider (OpenAI, OpenRouter, Groq, Ollama, Mistral)
- Or create the provider implementation (see "Adding a New Provider" section)

### 🔴 "Tools requested but provider X does not support tool calling"

**Cause**: Your chosen provider doesn't support function calling

**Solution**: 
- Switch to a provider that supports tools (OpenAI, Groq, Mistral, OpenRouter)
- Conversation continues without tools automatically

```bash
# Check if your current provider supports tools:
/model gpt-4  # Switch to OpenAI (supports tools)
```

### 🔴 "Temperature validation error"

**Cause**: Temperature value outside provider's valid range

**Solution**:
- Ollama: 0.0 - 2.0
- OpenAI: 0.0 - 2.0
- Groq: 0.0 - 2.0

```bash
# Fix temperature
/temperature 0.7  # Most providers accept this
```

### 🔴 "Connection refused" on Ollama

**Cause**: Ollama service not running

**Solutions**:
```bash
# Check if Ollama is running
curl http://localhost:11434

# If not running, start it:
ollama serve

# Then run Tiaga in another terminal
```

### 🔴 "No module named 'tiaga'"

**Cause**: Package not installed or virtual environment not activated

**Solutions**:
```bash
# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Reinstall package
pip install -e .
```

### 💡 "How do I switch providers mid-conversation?"

Just use the `/model` command:

```bash
You: /model gpt-4
# Response: Model changed to gpt-4
# Future requests use OpenAI

You: /model minimax/minimax-m2.5:free
# Response: Model changed to minimax (OpenRouter)
```

No restart needed! Settings save automatically.

---

## 📚 FAQ: New Users

**Q: Which provider should I start with?**
A: Use **Ollama** (free, local) or **Groq** (free tier, fast). OpenAI if you need the best quality.

**Q: Can I switch providers without restarting?**
A: Yes! Just use `/model provider/model-name` and Tiaga switches instantly.

**Q: Do I need an API key for Ollama?**
A: No! Ollama runs locally on your machine. No internet needed (optional).

**Q: What if a provider suddenly stops working?**
A: Tiaga automatically falls back gracefully. Check logs and try `/model gpt-4` to use OpenAI while troubleshooting.

**Q: Can I use my own LLM server?**
A: Yes! Use any **OpenAI-compatible API** with generic detection:
```toml
[model]
name = "any-model-name"
base_url = "http://your-server:8000/v1"  # Must be /v1 endpoint
api_key = "any-key"
```

**Q: How do I see latency/performance metrics?**
A: Tiaga shows latency info after each response:
```
Your response text here...

---
⏱️ Response latency: 2.34s
```

**Q: What's the difference between these providers?**
See the table in "Step 2: Get an API Key" above.

---

## Issue: "Provider 'xyz' not found, falling back to OpenAI-compatible"

**Cause**: Provider needs to be fully implemented

**Solution**: Create provider class and register in `provider_factory.py`

### Issue: "Tools requested but provider X does not support tool calling"

**Cause**: Provider doesn't support function calling

**Solution**: Conversation continues without tools (graceful degradation)

### Issue: Temperature validation error

**Cause**: Provider has different temperature range

**Solution**: Implement `validate_temperature()` in provider class

## Future Improvements

- [ ] Implement Anthropic provider
- [ ] Implement Gemini provider  
- [ ] Implement Cohere provider
- [ ] Tool format translation layer
- [ ] Vision support matrix
- [ ] Token counting per provider
- [ ] Rate limiting per provider
- [ ] Fallback provider chain
