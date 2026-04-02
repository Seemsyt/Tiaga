# Tiaga

**Author:** seems kushwaha ([@seemsyt](https://github.com/seemsyt))

Tiaga is a terminal AI assistant with a Python backend, LangGraph agent loop, SQLite-backed session history, and an experimental Ink frontend.

## What is supported

- Python chat CLI via `python -m tiaga` or `tiaga`
- Session persistence in `~/.tiaga/chat_history.db`
- File tools, web search, YouTube transcript lookup, and a text-only coding helper
- Ink frontend talking to the Python backend through `tiaga.bridge`

## Current frontend status

- `tiaga.main` is the stable entrypoint today
- `ink-cli/` is a real backend-connected rewrite, but it is still an active work-in-progress
- `prompt_toolkit_tui.py` is legacy exploration, not the default app

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Create a `.env` file in the repo root:

```env
OPEN_ROUTER_API_KEY=your_api_key_here
BASE_URL=https://openrouter.ai/api/v1
```

## Running the Python CLI

```bash
python -m tiaga
```

Or, after install:

```bash
tiaga
```

## Running the Ink CLI

The Ink frontend needs Node.js and npm installed locally.

```bash
cd ink-cli
npm install
npm run build
node dist/main.js
```

During development:

```bash
cd ink-cli
npm install
npm run dev
```

## Testing

Use this checklist after setup.

### 1. Backend install/import smoke test

```bash
pip install -e .
python -c "from tiaga.chat_engine import ChatEngine; print(ChatEngine()._normalize_thread_id(''))"
python -c "from tiaga.graph import model; print(type(model).__name__)"
```

Expected:

- first command prints `session`
- second command prints `ChatOpenAI`

### 2. Python syntax check

```bash
python -m compileall tiaga
```

### 3. Bridge smoke tests

If you want isolated tests that do not touch your real session DB, set `TIAGA_DB_PATH` to a temporary file.

List sessions:

```bash
env TIAGA_DB_PATH=/tmp/tiaga-test.db bash -lc "printf '{\"action\":\"list_sessions\"}\n' | python -m tiaga.bridge"
```

Load one session history:

```bash
env TIAGA_DB_PATH=/tmp/tiaga-test.db bash -lc "printf '{\"action\":\"get_history\",\"thread_id\":\"session-name\"}\n' | python -m tiaga.bridge"
```

Stream one chat turn:

```bash
env TIAGA_DB_PATH=/tmp/tiaga-test.db bash -lc "printf '{\"action\":\"chat\",\"thread_id\":\"smoke-test\",\"message\":\"say hello briefly\"}\n' | python -m tiaga.bridge"
```

Expected:

- JSON output
- chat requests end with `{"type": "done"}`
- no permission prompt events
- `get_history` only returns messages for a session that already exists

### 4. End-to-end Python CLI test

Run:

```bash
python -m tiaga
```

Then try:

- `what files are in the current directory?`
- `create a folder named tmp-demo`
- `delete the folder tmp-demo`

### 5. Ink frontend test

After Node.js is installed:

```bash
cd ink-cli
npm install
npm run build
node dist/main.js
```

Then verify:

- existing sessions load instead of mock sessions
- selecting a saved session loads history
- sending a message streams assistant text
- tool activity appears inline

## Project layout

```text
.
├── tiaga/
│   ├── __init__.py
│   ├── __main__.py
│   ├── bridge.py
│   ├── chat_engine.py
│   ├── graph.py
│   ├── main.py
│   ├── prompt_toolkit_tui.py
│   ├── stdio_bridge.py
│   ├── utils.py
│   ├── youtube_scrapping.py
│   └── files_handling/
│       └── file.py
├── ink-cli/
│   ├── src/
│   │   ├── commands/
│   │   ├── components/
│   │   ├── engine/
│   │   ├── main.tsx
│   │   └── types.ts
│   ├── package.json
│   ├── tsconfig.json
│   └── tsup.config.ts
├── .venv/
├── dist/
├── tiaga.egg-info/
├── .git/
├── .codex/
├── .env
├── .gitignore
├── .python-version
├── README.md
├── package-lock.json
├── pyproject.toml
├── test.html
├── test.py
├── test_tui.py
└── uv.lock
```
