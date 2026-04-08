from pydantic import BaseModel,Field
from tiaga.utils.path import is_binary, resolve_path
from ..base import Tool,Tool_kind, ToolInvocation,ToolResult
from tiaga.context.text import truncate_text
class ReadFileParams(BaseModel):
    path:str = Field(...,description="This the path to the file which can be read(it can be related to working directory  path or absolute path)(this is required)")

    offset:int = Field(...,ge=1,description="This the line number from where you should start reading file(1-based and required)")
    limit:int|None = Field(None,ge=1,description="maximum line you want to read from file . If not specified read entire file")

class ReadFileTool(Tool):
    name = "read_file"
    description = (
        "Read the contents of a text file. Returns the file content with line numbers. "
        "For large files, use offset and limit to read specific portions. "
        "Cannot read binary files (images, executables, etc.)."
    )
    tool_kind = Tool_kind.READ
    MAX_DISPLAY_OUTPUT_TOKENS = 25000
    schema = ReadFileParams
    MAX_SIZE = 1024*1024*10
    async def execute(self, invocation:ToolInvocation):
        params = ReadFileParams(**invocation.params)
        path = resolve_path(invocation.cwd,params.path)

        if not path.exists():
            return ToolResult.error_result(f"file not found at path{path}")
        if not path.is_file():
            return ToolResult.error_result(f"its not a file {path}")
        file_size = path.stat().st_size

        if file_size > self.MAX_SIZE :
            return ToolResult.error_result(f"file size is too large {file_size//1024*1024}")
        
        if is_binary(path=path):
            return ToolResult.error_result(f"can not read binary file  {path}")
        try:
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError as e :
                content = path.read_text(encoding="latin-1")

            lines = content.splitlines()
            total_lines = len(lines)

            if total_lines == 0 :
                return ToolResult.success_result(output="file is empty",kwargs={
                    "metadata":{
                        "lines":0,
                    }
                })
            start_idx = max(0,params.offset-1)
            if  params.limit:
                end_idx = min(start_idx+params.limit,total_lines)
            else :
                end_idx = total_lines

            selected_lines = lines[start_idx:end_idx]
            formated_lines = []
            for i,line in enumerate(selected_lines,start=start_idx+1):
                formated_lines.append(f"{i:6}| {line}")
            
            output = "\n".join(formated_lines)
            metadata_lines = []
            if start_idx >0 and end_idx<total_lines:
                metadata_lines.append(f"showing lines from {start_idx+1} to {end_idx}") 
            if metadata_lines:
                header = "|".join(metadata_lines) + "\n"
                output = header + output

            display_output = None
            is_truncated = False
            maybe_truncated = truncate_text(
                output,
                model="gpt-4o-mini",
                max_tokens=self.MAX_DISPLAY_OUTPUT_TOKENS,
                suffix="\n...[truncated for display]",
            )
            if maybe_truncated != output:
                display_output = maybe_truncated
                is_truncated = True

            return ToolResult.success_result(
                output=output,
                display_output=display_output,
                truncated=is_truncated,
                metadata = {
                    "path":str(path),
                    "total_lines":total_lines,
                    "shown_start":start_idx + 1,
                    "shown_end":end_idx

                }

            )
        except Exception as e :
            return ToolResult.error_result(f"failed to read file {str(e)}")




        
        
