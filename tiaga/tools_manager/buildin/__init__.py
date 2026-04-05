from tools_manager.buildin.readfile import ReadFileTool

__all__=[
    "ReadFileTool"
]
def get_all_builtin_tool()->list[type]:
    return [
        ReadFileTool
        ]