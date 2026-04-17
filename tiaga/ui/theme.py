"""
ui/theme.py
-----------
Single source of truth for colours, CSS variables and Rich theme.
Matches the dark teal/green aesthetic from the reference screenshots.
"""

from rich.theme import Theme

# ── Textual CSS variables (injected into DEFAULT_CSS) ────────────────────────
TEXTUAL_CSS = """
/* ── global ──────────────────────────────────────────────────────────── */
Screen {
    background: #1a1e2e;
    color: #cdd6f4;
}

/* ── header bar ──────────────────────────────────────────────────────── */
#header {
    height: 1;
    background: #1a1e2e;
    border-bottom: tall #2a2e3e;
    padding: 0 1;
    layout: horizontal;
    align: left middle;
}
#header-title {
    color: #cba6f7;
    text-style: bold;
}
#header-path {
    color: #6c7086;
    padding: 0 1;
}
#header-mode {
    dock: right;
    color: #6c7086;
    padding: 0 1;
}

/* ── top rainbow border ───────────────────────────────────────────────── */
#rainbow-border {
    height: 1;
    background: transparent;
}

/* ── main scroll area ─────────────────────────────────────────────────── */
#messages-scroll {
    padding: 0 2;
    scrollbar-size: 1 1;
    scrollbar-color: #45475a;
    scrollbar-background: #1e2030;
}

/* ── tool call blocks ─────────────────────────────────────────────────── */
.tool-block {
    margin: 0 0 1 0;
    border: tall #2a4a3a;
    background: #1e2a20;
    padding: 0 1;
}
.tool-block--running {
    border: tall #3a6a4a;
}
.tool-block--success {
    border: tall #2a9a5a;
}
.tool-block--error {
    border: tall #9a3a3a;
}
.tool-header {
    color: #a6e3a1;
    text-style: bold;
    padding: 0 0 0 0;
}
.tool-header--error {
    color: #f38ba8;
}
.tool-args {
    color: #6c7086;
    padding: 0 0 0 2;
}
.tool-output {
    background: #161a20;
    padding: 0 1;
    color: #cdd6f4;
    margin: 0 0 0 0;
}
.tool-shell-cmd {
    color: #a6e3a1;
    padding: 0 0 0 1;
    text-style: bold;
}
.tool-subtitle {
    color: #6c7086;
    text-align: right;
}

/* ── assistant text ───────────────────────────────────────────────────── */
.assistant-text {
    color: #cdd6f4;
    padding: 0 0 1 0;
}

/* ── plan panel ───────────────────────────────────────────────────────── */
.plan-panel {
    border: tall #3a3a6a;
    background: #1e1e35;
    margin: 1 0;
    padding: 0 1;
}
.plan-title {
    color: #89b4fa;
    text-style: bold;
    padding: 0 0 0 0;
}
.plan-item {
    color: #cdd6f4;
    padding: 0 0 0 1;
}
.plan-item--active {
    color: #89b4fa;
    text-style: bold;
}
.plan-item--done {
    color: #6c7086;
}

/* ── input bar ────────────────────────────────────────────────────────── */
#input-bar {
    height: 3;
    border: tall #2a2e3e;
    background: #1e2030;
    padding: 0 1;
    layout: horizontal;
    align: left middle;
    margin: 0 0 0 0;
}
#chat-input {
    background: transparent;
    border: none;
    padding: 0 1;
    color: #cdd6f4;
    width: 1fr;
}
#chat-input:focus {
    border: none;
    background: transparent;
}
.input-hint {
    color: #45475a;
    padding: 0 1;
}
.input-hint--key {
    color: #585b70;
    text-style: bold;
}

/* ── footer keybindings ───────────────────────────────────────────────── */
#footer {
    height: 1;
    background: #181825;
    padding: 0 1;
    layout: horizontal;
    align: left middle;
}
.footer-key {
    color: #89b4fa;
    text-style: bold;
    padding: 0 0;
}
.footer-label {
    color: #6c7086;
    padding: 0 1 0 0;
}

/* ── diff / approval view ─────────────────────────────────────────────── */
#approval-screen {
    layout: horizontal;
}
#approval-sidebar {
    width: 18;
    border-right: tall #2a2e3e;
    background: #1a1e2e;
    padding: 1 1;
}
.approval-option {
    padding: 0 1;
    color: #cdd6f4;
    margin: 0 0 0 0;
}
.approval-option--selected {
    border: tall #cba6f7;
    color: #cba6f7;
    text-style: bold;
}
.approval-option--key {
    color: #585b70;
    padding: 0 0 0 0;
}
#approval-files {
    padding: 1 1;
    color: #6c7086;
}
#diff-view {
    width: 1fr;
    border: none;
    padding: 0 0;
}
#diff-header {
    background: #1e2030;
    padding: 0 1;
    color: #6c7086;
    height: 2;
    border-bottom: tall #2a2e3e;
}
.diff-filename {
    color: #cdd6f4;
}
.diff-stat-add {
    color: #a6e3a1;
    text-style: bold;
}
.diff-stat-del {
    color: #f38ba8;
    text-style: bold;
}
#diff-content {
    padding: 0 0;
    overflow: auto;
}
"""

# ── Rich theme (used inside Static/renderables) ───────────────────────────────
RICH_THEME = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "bright_red bold",
        "success": "#a6e3a1",
        "dim": "dim",
        "muted": "#6c7086",
        "border": "#45475a",
        "highlight": "bold #cba6f7",
        # Roles
        "user": "#89b4fa bold",
        "assistant": "#cdd6f4",
        # Tools
        "tool": "#a6e3a1 bold",
        "tool.read": "#89b4fa",
        "tool.write": "#f9e2af",
        "tool.shell": "#cba6f7",
        "tool.network": "#74c7ec",
        "tool.memory": "#a6e3a1",
        "tool.mcp": "#94e2d5",
        # Code
        "code": "#cdd6f4",
    }
)

# Tool kind → colour tag used in CSS classes and Rich markup
TOOL_KIND_COLOR: dict[str, str] = {
    "read": "#89b4fa",
    "write": "#f9e2af",
    "shell": "#cba6f7",
    "network": "#74c7ec",
    "memory": "#a6e3a1",
    "mcp": "#94e2d5",
    "": "#a6e3a1",
}