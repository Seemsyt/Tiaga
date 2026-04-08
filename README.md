# Tiaga

**Author:** seemsyt (Seems Kushwaha)

Tiaga is a terminal AI assistant focused on coding and tool-assisted workflows in your local workspace.

## Features

- Interactive CLI assistant
- Built-in tools for file operations, shell commands, search, and web fetch
- Configurable model, API key, and base URL from slash commands
- Local config loading from user and project scopes

## Installation

Create and activate a virtual environment, then install:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Set environment variables (or use `/config` commands at runtime):

```env
API_KEY=your_api_key_here
BASE_URL=https://openrouter.ai/api/v1
```

## Run

After install:

```bash
tiaga
```

Or directly:

```bash
python -m tiaga.main
```

## CLI Commands

- `/help`
- `/exit`
- `/config show`
- `/config model <model_name>`
- `/config base_url <url>`
- `/config api_key <key>`
- `/model` (shows current model and token usage)
- `/model <model_name>` (updates model)

## Config Resolution

Tiaga loads config in this order:

1. User config: `user_config_dir("seems-tiaga")/config.toml`
2. Project config: `<cwd>/.seems-tiaga/config.toml` (overrides user config)

If config directories are missing, Tiaga handles it safely and creates folders when writing config.

## Quick Check

```bash
python -m compileall tiaga
```

## Project Layout

```text
.
├── tiaga/
│   ├── __init__.py
│   ├── main.py
│   ├── agent/
│   │   ├── agent.py
│   │   ├── events.py
│   │   └── session.py
│   ├── client/
│   │   ├── llm_client.py
│   │   └── response.py
│   ├── config/
│   │   ├── config.py
│   │   └── loader.py
│   ├── context/
│   │   ├── manager.py
│   │   ├── prompts.py
│   │   └── text.py
│   ├── tools_manager/
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── subagent.py
│   │   └── buildin/
│   │       ├── readfile.py
│   │       ├── writefile.py
│   │       ├── editfile.py
│   │       ├── shell.py
│   │       ├── listdir.py
│   │       ├── grep.py
│   │       ├── glob.py
│   │       ├── websearch.py
│   │       ├── webfetch.py
│   │       ├── youtube_scrapping.py
│   │       ├── todo.py
│   │       └── memory.py
│   ├── ui/
│   │   └── render.py
│   └── utils/
│       ├── erors.py
│       └── path.py
├── README.md
├── pyproject.toml
└── uv.lock
```
