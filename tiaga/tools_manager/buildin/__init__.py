from tiaga.tools_manager.buildin.readfile import ReadFileTool
from tiaga.tools_manager.buildin.writefile import WriteFileTool
from tiaga.tools_manager.buildin.editfile import EditFileTool
from tiaga.tools_manager.buildin.shell import ShellTool
from tiaga.tools_manager.buildin.listdir import ListDir
from tiaga.tools_manager.buildin.grep import GrepTool
from tiaga.tools_manager.buildin.glob import GlobTool
from tiaga.tools_manager.buildin.websearch import WebSearchTool
from tiaga.tools_manager.buildin.webfetch import WebFetchTool
from tiaga.tools_manager.buildin.youtube_scrapping import YouTubeTranscriptTool
from tiaga.tools_manager.buildin.todo import TodosTool
from tiaga.tools_manager.buildin.memory import MemoryTool
__all__=[
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "ShellTool",
    "ListDir",
    "GrepTool",
    "GlobTool" ,
    "WebSearchTool",
    "WebFetchTool",
    "YouTubeTranscriptTool",
    "TodosTool",
    "MemoryTool",
]
def get_all_builtin_tool()->list[type]:
    return [
        ReadFileTool,
        WriteFileTool,
        EditFileTool,
        ShellTool,
        ListDir,
        GrepTool,
        GlobTool,
        WebSearchTool,
        YouTubeTranscriptTool,
        WebFetchTool,
        TodosTool,
        MemoryTool,

        ]
