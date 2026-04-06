from tiaga.tools_manager.buildin.readfile import ReadFileTool
from tiaga.tools_manager.buildin.writefile import WriteFileTool
from tiaga.tools_manager.buildin.editfile import EditFileTool
from tiaga.tools_manager.buildin.shell import ShellTool

__all__=[
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "ShellTool",
]
def get_all_builtin_tool()->list[type]:
    return [
        ReadFileTool,
        WriteFileTool,
        EditFileTool,
        ShellTool,
        ]
