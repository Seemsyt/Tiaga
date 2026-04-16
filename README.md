# Tiaga

**Author:** Seems Kushwaha (seemsyt)

Tiaga is a powerful terminal-based AI assistant designed for coding and tool-assisted workflows in your local workspace. It provides an interactive TUI interface with comprehensive tool support, session persistence, and advanced configuration options.

## Features

- **Interactive TUI Interface**: Rich terminal UI with real-time streaming responses
- **Built-in Tools**: File operations (read, write, edit), shell execution, directory listing, search (grep, glob), web search, web fetch, YouTube transcript, todo management, memory storage
- **MCP Support**: Model Context Protocol server integration for extended capabilities
- **Session Persistence**: Save, resume, and checkpoint conversations
- **Hooks System**: Execute custom commands/scripts at various trigger points
- **Approval Policies**: Configurable approval for tool execution (on_request, on_failure, auto, auto_edit, never, yolo)
- **Smart Context Management**: Automatic context compression when window limit is approached
- **Loop Detection**: Prevents repetitive tool calls
- **Multi-provider Support**: Compatible with OpenAI-style APIs (OpenRouter, etc.)
- **Config Scopes**: User-level and project-level configuration
- **Shell Environment Control**: Configurable environment variables and exclusion patterns
- **Developer Instructions**: Custom system prompts at user and developer levels

## Installation

Using pip:

```bash
pip install tiaga or pipx install tiaga
```

Or from source:

```bash
git clone <repository>
cd tiaga
pip install -e .
```

## Configuration

### Environment Variables

Set these before running:

```env
API_KEY=your_api_key_here
BASE_URL=https://openrouter.ai/api/v1
```

Optional environment variable:
- `TIAGA_DEBUG=1` - Enable debug logging

### Configuration File

Tiaga supports TOML configuration at two levels:

1. **User config**: `~/.local/share/seems-tiaga/config.toml` (Linux) or equivalent
2. **Project config**: `<project>/.seems-tiaga/config.toml` (overrides user config)

Example `config.toml`:

```toml
[model]
name = "stepfun/step-3.5-flash:free"
temperature = 1.0

[approval]
policy = "on_request"  # or "on_failure", "auto", "auto_edit", "never", "yolo"

[cwd]
path = "/path/to/working/directory"

[shell_environment]
excludes_patterns = ["*KEY*", "*TOKEN*", "*SECRET*"]
set_vars = { "CUSTOM_VAR" = "value" }

[mcp_servers.example]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/files"]

[hooks.pre_agent]
trigger = "before_agent"
command = "python3 hooks/before_agent.py"
timeout_sec = 10
enabled = true

[max_turns] = 100
[max_output_tokens] = 50000
[debug] = true
```

## Usage

### Interactive Mode

```bash
tiaga
```

Or with specific working directory:

```bash
tiaga --cwd /path/to/project
```

### Single Prompt Mode

```bash
tiaga "Write a Python function to calculate fibonacci numbers"
```

### Command-line Options

- `--cwd, -c`: Set the working directory (must exist)

## CLI Commands

During interactive sessions, use these slash commands:

### Navigation & Control
- `/help` - Show help
- `/exit`, `/quit`, `/q` - Exit Tiaga
- `/clear` - Clear conversation history and loop detector state

### Configuration
- `/config` - Show current configuration
- `/config model <name>` - Change model
- `/config base_url <url>` - Change base URL
- `/config api_key <key>` - Change API key
- `/config approval <policy>` - Change approval policy (on_request, on_failure, auto, auto_edit, never, yolo)

### Model Management
- `/model` - Show current model and token usage
- `/model <name>` - Switch to a different model

### Tools
- `/tools` - List all available tools
- `/mcp` - List MCP servers

### Session Persistence
- `/save` - Save current session
- `/sessions` - List all saved sessions
- `/resume <session_id>` - Resume a saved session
- `/checkpoint` - Create a checkpoint of current session
- `/checkpoints <session_id>` - List checkpoints for a session
- `/restore <checkpoint_id>` - Restore from a checkpoint

### Debug & Stats
- `/stats` - Show session statistics (turns, tool calls, token usage, etc.)

## CLI Commands Reference

| Command | Description |
|---------|-------------|
| `/help` | Show this help message |
| `/exit` / `/quit` / `/q` | Exit the application |
| `/clear` | Clear conversation history |
| `/config` | Display current configuration |
| `/config model <name>` | Set LLM model |
| `/config base_url <url>` | Set API base URL |
| `/config api_key <key>` | Set API key |
| `/config approval <policy>` | Set approval policy |
| `/model` | Show current model and usage |
| `/model <name>` | Change model |
| `/tools` | List available tools |
| `/mcp` | List MCP servers |
| `/save` | Save session to disk |
| `/sessions` | List saved sessions |
| `/resume <id>` | Resume a saved session |
| `/checkpoint` | Create checkpoint |
| `/checkpoints <session_id>` | List checkpoints |
| `/restore <checkpoint_id>` | Restore from checkpoint |
| `/stats` | Show session statistics |
| `/approval` | Show/change approval policy |

## Approval Policies

Control when tool executions require user approval:

- `on_request` (default) - Ask for approval for each tool call
- `on_failure` - Auto-approve, ask only if tool fails
- `auto` - Auto-approve all tools (use with caution)
- `auto_edit` - Auto-approve only file edit tools
- `never` - Never ask for approval (not recommended)
- `yolo` - No approval, no safety checks (dangerous!)

Set with: `/config approval <policy>` or in config file.

## Built-in Tools

Tiaga includes these tools by default:

| Tool | Description |
|------|-------------|
| `readfile` | Read file contents |
| `writefile` | Write content to a file |
| `editfile` | Edit file with search/replace |
| `shell` | Execute shell commands |
| `listdir` | List directory contents |
| `grep` | Search text in files |
| `glob` | Find files by pattern |
| `websearch` | Search the web (DuckDuckGo) |
| `webfetch` | Fetch URL content |
| `youtube_scrapping` | Get YouTube video transcript |
| `todo` | Manage task list |
| `memory` | Store/retrieve persistent memory |

## Project Layout

```text
tiaga/
├── __init__.py           # Package init with warnings setup
├── main.py               # CLI entry point, command handling
├── hello.py              # Simple hello function
├── dummy_script.py       # Example script
│
├── agent/                # Agent orchestration
│   ├── agent.py          # Core Agent class with run loop
│   ├── events.py         # AgentEvent types and definitions
│   ├── session.py        # Session management, tool registry
│   └── persistence.py    # Session checkpoint/save/load
│
├── client/               # LLM client layer
│   ├── llm_client.py     # OpenAI-compatible client
│   └── response.py       # Response parsing, token usage
│
├── config/               # Configuration management
│   ├── config.py         # Config model (pydantic)
│   └── loader.py         # Config loading & merging
│
├── context/              # Conversation context
│   ├── manager.py        # Message history, token counting
│   ├── prompts.py        # System prompts, loop breaker
│   ├── text.py           # Text utilities
│   └── compaction.py     # Context compression
│
├── hooks/                # Hook system
│   └── hook_system.py    # Hook trigger management
│
├── safty/                # Safety/approval (note: typo in dir name)
│   └── approval.py       # Approval manager, callbacks
│
├── scripts/              # Utility scripts
│   └── test_tool.py      # Tool testing script
│
├── tools_manager/        # Tool infrastructure
│   ├── base.py           # Base Tool class, ToolResult
│   ├── registry.py       # ToolRegistry, tool discovery
│   ├── subagent.py       # Sub-agent tool wrapper
│   ├── discovery.py      # Tool discovery utilities
│   ├── buildin/          # Built-in tools (12 tools)
│   │   ├── readfile.py
│   │   ├── writefile.py
│   │   ├── editfile.py
│   │   ├── shell.py
│   │   ├── listdir.py
│   │   ├── grep.py
│   │   ├── glob.py
│   │   ├── websearch.py
│   │   ├── webfetch.py
│   │   ├── youtube_scrapping.py
│   │   ├── todo.py
│   │   └── memory.py
│   ├── mcp/              # MCP server integration
│   │   ├── manager.py
│   │   ├── transport.py
│   │   └── types.py
│   └── __init__.py
│
├── ui/                   # User interface
│   ├── render.py         # TUI rendering, panels, streaming
│   └── __init__.py
│
└── utils/                # Utilities
    ├── config_setter.py  # Empty module
    ├── erors.py          # Custom exceptions
    ├── path.py           # Path utilities
    └── __init__.py

# Root level files
├── pyproject.toml        # Project metadata, dependencies
├── uv.lock               # Dependency lock file
├── README.md             # This file
├── test.py               # Simple test
└── dist/                 # Build artifacts
```

## Development

### Quick Check

Verify the package compiles:

```bash
python -m compileall tiaga
```

### Running Tests

```bash
python test.py
```

### Building

```bash
pip install build
python -m build
```

## How It Works

1. **Initialization**: Loads config from user and project scopes, sets up LLM client
2. **Session Creation**: Creates a session with context manager, tool registry, and MCP manager
3. **Message Processing**: User input is added to context, agent enters loop:
   - Get tool schemas from registry
   - Call LLM with context
   - Stream response back to user
   - Execute any tool calls (with approval if required)
   - Add tool results to context
   - Check for context compression need
   - Repeat up to `max_turns`
4. **Event Streaming**: Events (tool calls, text deltas, completions, errors) are yielded and rendered in TUI
5. **Persistence**: Sessions can be saved and resumed at any point

## Extensibility

### Adding Custom Tools

Create a Python file and register tools using the `@tool` decorator:

```python
from tiaga.tools_manager.base import tool, Tool
from pydantic import BaseModel

class MyInput(BaseModel):
    param: str

@tool
def my_tool(input: MyInput) -> str:
    """Tool description"""
    return f"Result for {input.param}"
```

### Adding MCP Servers

Configure in `config.toml`:

```toml
[mcp_servers.my_server]
command = "path/to/mcp/server"
args = ["--flag", "value"]
```

## License

MIT
