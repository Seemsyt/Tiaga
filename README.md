# Tiaga

A powerful AI assistant CLI application built with LangGraph, featuring advanced file operations, web search, and coding capabilities.

![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
[![GitHub stars](https://img.shields.io/github/stars/seemsyt/tiaga?style=social)](https://github.com/yourusername/tiaga)

## ✨ Features

- **Interactive AI Chat**: Engage in natural conversations with an AI assistant powered by large language models
- **Session Management**: Save, resume, and manage multiple conversation sessions with persistent history
- **File Operations**: Read, write, create, delete, move files and folders directly through conversation
- **Web Search**: Integrated DuckDuckGo search for up-to-date information
- **Coding Assistant**: Specialized coding agent for programming tasks
- **Beautiful Terminal UI**: Rich console interface with tables, panels, and colored output
- **Persistent History**: SQLite-based checkpointing saves conversation context across sessions
- **Tool Calling**: AI can intelligently decide when to use tools based on user requests
- **Streaming Responses**: Real-time streaming of AI responses for smooth interaction

## 🏗️ Architecture

Tiaga is built using modern Python libraries and follows a modular architecture:

```
tiaga/
├── main.py              # CLI interface, session management, UI
├── graph.py             # LangGraph workflow definition, tool binding
├── files_handling/
│   └── file.py          # File operation tools (read, write, etc.)
├── pyproject.toml       # Project metadata and dependencies
├── .env                 # Environment variables (API keys)
├── chat_history.db      # SQLite checkpoint storage
├── test.py              # Test scripts
└── README.md            # This file
```

### How It Works

1. **Main Loop** (`main.py`):
   - Session selection (new or resume existing)
   - User input collection with Rich prompts
   - Streaming response display
   - Error handling and graceful exit

2. **Graph Workflow** (`graph.py`):
   - `ChatState`: TypedDict holding conversation messages
   - `chat_node`: LLM with bound tools
   - `tools_node`: Executes tool calls
   - Conditional routing: if tools needed → run tools → back to chat
   - Checkpointing with `AsyncSqliteSaver` for persistence

3. **Tools**:
   - **Search**: `DuckDuckGoSearchResults` for web queries
   - **Coding**: `coding_agent` for programming tasks
   - **File Operations**: 11 file system tools (read_file, write_file, create_folder, etc.)

## 📦 Installation

### Prerequisites

- Python 3.9 or higher(3.12 recommended)
- Git (optional)

### Setup Steps

1. **Clone the repository** (if from GitHub):
```bash
git clone https://github.com/seems-dev/tiaga.git
cd tiaga
```

2. **Create virtual environment** (recommended):
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. **Install dependencies**:
```bash
pip install -e .
```

Or install manually:
```bash
pip install ddgs duckduckgo-search fastapi langchain langchain-community \
    langchain-openai langchain-tavily langgraph langgraph-checkpoint-sqlite \
    mcp tavily-python typer rich python-dotenv aiosqlite
```

4. **Configure environment variables**:
Create a `.env` file in the project root:
```env
OPEN_ROUTER_API_KEY=your_api_key_here
BASE_URL=https://openrouter.ai/api/v1
```

You can get an API key from [OpenRouter](https://openrouter.ai/).

## 🚀 Usage

Start the interactive chat:
```bash
python -m tiaga
# or
python main.py
```
```
Or you can create you executable file running this script directly from your terminal
```
### First Run

1. You'll see a list of past sessions (if any) or a message that no sessions exist
2. Enter a new session name or pick a number to resume
3. Start typing your messages!

### Example Interactions

```
Session: my_first_chat
you: What's the current weather in London?
assistant: [Uses search tool] The current weather in London is...

you: Create a file called 'todo.txt' with content: "Buy groceries"
assistant: [Uses write_file] Written: '/path/to/todo.txt'

you: Read that file
assistant: [Uses read_file] Content: Buy groceries

you: Write a Python function to calculate factorial
assistant: [Uses coding_agent] Here's a factorial function...
```

### Controls

- Type `exit`, `quit`, or `bye` to end the session
- Type `help` (future feature) for command list
- Use Ctrl+C to interrupt
- Sessions are automatically saved; resume anytime

## 🔧 Configuration

### Changing the LLM Model

Edit `graph.py` to use a different model:

```python
model = ChatOpenAI(
    model='anthropic/claude-3-haiku',  # Change model
    api_key=getenv("OPEN_ROUTER_API_KEY"),
    base_url=getenv("BASE_URL"),
    streaming=True,
    temperature=0.7
)
```

See available models on [OpenRouter](https://openrouter.ai/models).

### Adjusting System Prompt

Modify the `SYSTEM_PROMPT` in `graph.py` to change assistant behavior:

```python
SYSTEM_PROMPT = SystemMessage(
    content="""
You are a specialized coding assistant.
Always provide detailed explanations.
...
"""
)
```

### Adding Custom Tools

Add new tools to the `tools` list in `graph.py`:

```python
@tool
def my_custom_tool(param: str) -> str:
    """Tool description"""
    # Implementation
    return result

tools = [search_tool, coding_agent, my_custom_tool, ...]
```

## 🧪 Testing

Run the test script:
```bash
python test.py
```

## 📁 Project Structure

```
├── .venv/                    # Virtual environment (gitignored)
├── __pycache__/              # Python cache (gitignored)
├── cli interfance manger/    # (Legacy/organizational folder)
│   └── hello.py
├── files_handling/           # File operation tools
│   ├── __pycache__/
│   └── file.py
├── .env                      # Environment variables (gitignored)
├── .gitignore
├── .python-version
├── README.md                 # This file
├── chat_history.db           # SQLite checkpoint storage (auto-created)
├── chat_history.db-shm
├── chat_history.db-wal
├── graph.py                  # LangGraph workflow
├── main.py                   # CLI entry point
├── pyproject.toml            # Project config
├── test.html
├── test.py
└── uv.lock
```

## 🛠️ Development

### Adding New File Tools

1. Open `files_handling/file.py`
2. Decorate a function with `@tool`
3. Add proper docstring (used by AI to understand tool)
4. Import and add to `tools` list in `graph.py`

### Debugging

- Check `.env` for API keys
- Ensure `chat_history.db` is writable
- Use `file_tree()` tool to explore project structure
- View logs in terminal for errors

## 📄 License

MIT License - see LICENSE file for details.

## 🙏 Acknowledgments

- [LangChain](https://github.com/langchain-ai/langchain) & [LangGraph](https://github.com/langchain-ai/langgraph)
- [OpenRouter](https://openrouter.ai/) for unified API access
- [Rich](https://github.com/Textualize/rich) for beautiful terminal output
- [Typer](https://typer.tiangolo.com/) for CLI interface

## 📮 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

For major changes, please open an issue first to discuss.

## 📧 Support

If you encounter issues or have questions:

1. Check the `test.py` for usage examples
2. Review tool documentation in `files_handling/file.py`
3. Open an issue on GitHub with:
   - Python version
   - Error message
   - Steps to reproduce

---

**Made with ❤️ using Python, LangGraph, and LLM models**
**Author Seems Kushwaha & (seems-dev)**
