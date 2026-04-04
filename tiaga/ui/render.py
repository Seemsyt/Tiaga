
from rich.text import Text
from rich.console import Console
from rich.rule import Rule
from rich.theme import Theme
AGENT_THEME = Theme(
    {
        # General
        "info": "cyan",
        "warning": "yellow",
        "error": "bright_red bold",
        "success": "green",
        "dim": "dim",
        "muted": "grey50",
        "border": "grey35",
        "highlight": "bold cyan",
        # Roles
        "user": "bright_blue bold",
        "assistant": "bright_white",
        # Tools
        "tool": "bright_magenta bold",
        "tool.read": "cyan",
        "tool.write": "yellow",
        "tool.shell": "magenta",
        "tool.network": "bright_blue",
        "tool.memory": "green",
        "tool.mcp": "bright_cyan",
        # Code / blocks
        "code": "white",
    }
)

_console :Console|None = None

def _get_console():
    global _console
    if _console is None:
        _console = Console(theme=AGENT_THEME,highlight=False)
    return _console
    
class TUI:
    def __init__(self,console:Console|None = None)->None:
       self.console = console or _get_console()
       self.assistance_stream_open = False

    def begin_streaming(self):
        self.console.print()
        self.console.print(Rule(Text("Assistance",style='assistant')))
        self.assistance_stream_open = True
    def stream_assistant_delta(self,content):
        self.console.print(content,end="",markup=False)

    def end_assistance(self):
        if self.assistance_stream_open:
            self.console.print()
        self.assistance_stream_open = False