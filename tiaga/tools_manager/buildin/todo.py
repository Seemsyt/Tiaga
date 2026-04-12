


import uuid

from pydantic import BaseModel
from pydantic import Field

from tiaga.config.config import Config
from tiaga.context.text import truncate_text
from tiaga.tools_manager.base import Tool, Tool_kind, ToolInvocation, ToolResult



class TodosParams(BaseModel):
    action: str = Field(...,description="Action: 'add', 'complete', 'list', 'clear'")
    id:str|None = Field(None,description="Todo for (for complete)")
    content:str|None = Field(None,description='Todo content (for add )')
    


class TodosTool(Tool):
    name = "todos"
    description = "Manage a task list for the current session. Use this to track progress on multi-step tasks."
    tool_kind = Tool_kind.MEMORY
    schema = TodosParams

    def __init__(self, config:Config)->None:
        super().__init__(config)
        self._todos:dict[str,str] = {}
    async def execute(self, invocation:ToolInvocation)->ToolResult:
        params = TodosParams(**invocation.params)

        if params.action.lower() == "add":

            if not params.content:
                return ToolResult.error_result(f"todo can not be added because content is absent : {params.content}")
            todo_id = str(uuid.uuid4())
            self._todos[todo_id] = params.content
            return ToolResult.success_result(f"added todo [{todo_id}]:{params.content}")
        elif params.action.lower() == "complete" :
            if not params.id:
                 return ToolResult.error_result("`id` required for 'complete' action")
            if params.id not in self._todos:
                return ToolResult.error_result(f"Todo not found: {params.id}")
            content = self._todos.pop(params.id)
            return ToolResult.success_result(f"Completed todo [{params.id}]: {content}")
        
        
        elif params.action == "list":
            if not self._todos:
                return ToolResult.success_result("No todos")
            lines = ["Todos:"]

            for todo_id, content in self._todos.items():
                lines.append(f"  [{todo_id}] {content}")
            return ToolResult.success_result("\n".join(lines))
        elif params.action == "clear":
            count = len(self._todos)
            self._todos.clear()
            return ToolResult.success_result(f"Cleared {count} todos")
        else:
            return ToolResult.error_result(f"Unknown action: {params.action}")
        


        