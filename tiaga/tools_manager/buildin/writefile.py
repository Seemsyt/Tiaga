from pydantic import BaseModel,Field
from tiaga.tools_manager.base import FileDiff, Tool, Tool_kind, ToolConfirmation, ToolInvocation, ToolResult
from tiaga.utils.path import resolve_path,ensure_parent_directory

class WriteFileParams(BaseModel):
    path: str = Field(
        ...,
        description="Path to the file to write (relative to working directory or absolute)",
    )
    content: str = Field(..., description="Content to write to the file")
    create_directories: bool = Field(
        True, description="Create parent directories if they don't exist"
    )

class WriteFileTool(Tool) :
    name = 'write_file'
    description = (
        "Write content to a file. Creates the file if it doesn't exist, "
        "or overwrites if it does. Parent directories are created automatically. "
        "Use this for creating new files or completely replacing file contents. "
        "For partial modifications, use the edit tool instead."
    )
    tool_kind = Tool_kind.WRITE
    schema = WriteFileParams

    async def get_confirmation(self, invocation:ToolInvocation)->ToolConfirmation|None:
        params = WriteFileParams(**invocation.params)
        path = resolve_path(invocation.cwd,params.path)

        is_new_file = not path.exists()
        action = "created" if is_new_file else "updated"

        old_content = " "
        if not is_new_file:
            try:
                old_content = path.read_text(encoding='utf-8')
            except:
                pass

        diff = FileDiff(path,old_content=old_content,new_content=params.content,is_new_file=is_new_file)
        return ToolConfirmation(
            tool_name=self.name,
            params=invocation.params,
            description=f"action {action} path{path}",
            diff=diff,
            affected_paths=[path],
            is_dangerous= not is_new_file

        )

    async def execute(self, invocation:ToolInvocation)->ToolResult:
        params = WriteFileParams(**invocation.params)
        path = resolve_path(invocation.cwd,params.path)

        is_new_file = not path.exists()
        old_content = ""
        if not is_new_file:
            try:
                old_content = path.read_text(encoding='utf-8')
            except:
                old_content = ""
        try:
            if params.create_directories:
                ensure_parent_directory(path)
            elif not path.parent.exists():
                return ToolResult.error_result(f"parent directory does not exists {path.parent}")
            path.write_text(params.content,encoding="utf-8")
            action = "created" if is_new_file else "updated"
            lines = len(params.content.splitlines())


            return ToolResult.success_result(f"{action} {path} {lines} lines",
                                            diff=FileDiff(path=path,old_content=old_content,new_content=params.content,is_new_file=is_new_file),
                                            metadata={
                                               "path": str(path),
                                                "is_new_file":is_new_file,
                                                "lines":lines,
                                                "bytes":len(params.content.encode("utf-8")),


                                            }
                                            
                                    )
        except OSError as e:
            return ToolResult.error_result(f"failed to write file: {e}")


            
        
