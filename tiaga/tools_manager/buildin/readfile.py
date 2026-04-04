from pydantic import BaseModel,Field
from ...utlis.path import is_binary, resolve_path
from ..base import Tool,Tool_kind, ToolInvocation,ToolResult

class ReadFileParams(BaseModel):
    path:str = Field(...,description="This the path to the file which can be read(it can be related to working directory  path or absolute path)(this is required)")

    offset = Field(...,ge=1,description="This the line number from where you should start reading file(1-based and required)")
    limit = Field(None,ge=1,description="maximum line you want to read from file . If not specified read entire file")

class ReadFileTool(Tool):
    name = "read_file"
    description = (
        "Read the contents of a text file. Returns the file content with line numbers. "
        "For large files, use offset and limit to read specific portions. "
        "Cannot read binary files (images, executables, etc.)."
    )
    tool_kind = Tool_kind.READ

    schema = ReadFileParams
    MAX_SIZE = 1024*1024*10
    async def execute(self, invocation:ToolInvocation):
        params = ReadFileParams(**invocation.params)
        path = resolve_path(invocation.cwd,params.path)

        if not path.exists():
            return ToolResult.error_result(f"file not found at path{path}")
        if not path.is_file:
            return ToolResult.error_result(f"its not a file {path}")
        file_size = path.stat().st_size

        if file_size > self.MAX_SIZE :
            return ToolResult.error_result(f"file size is too large {file_size//1024*1024}")
        
        if is_binary(path=path):
            return ToolResult.error_result(f"can not read binary file  {path}")
        

