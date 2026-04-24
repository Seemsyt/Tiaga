from __future__ import annotations
from abc import ABC
import abc
from dataclasses import dataclass, field
from typing import Any
from pydantic import BaseModel, ValidationError
from enum import Enum
from pathlib import Path
from pydantic.json_schema import model_json_schema
import difflib

from tiaga.config.config import Config
@dataclass
class ToolInvocation:
    params:dict[str,Any]
    cwd : Path
    parent_client: Any = None

@dataclass
class FileDiff:
    path:str
    old_content:str
    new_content:str

    is_new_file:bool = False
    is_deletion:bool = False

    def create_diff(self)->str:
        old_lines = self.old_content.splitlines(keepends=True)
        new_lines = self.new_content.splitlines(keepends=True)

        if old_lines and not old_lines[-1].endswith("\n"):
            old_lines[-1] += '\n'
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += '\n'
        old_name = "/dev/null" if self.is_new_file else str(self.path)
        new_name = "/dev/null" if self.is_deletion else str(self.path)

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=old_name,
            tofile=new_name,
        )
        return ''.join(diff)
        
@dataclass
class ToolResult:
    success:bool
    output:str
    error:str|None = None
    metadata: dict[str,Any] = field(default_factory=dict)

    truncated: bool = False
    display_output: str | None = None
    diff:FileDiff|None = None
    exit_code: int | None = None

    @classmethod
    def error_result(
        cls,error:str,output:str = "",
        **kwargs,
    ):
        return cls(success=False,output=output,error=error)
    @classmethod
    def success_result(cls, output: str = "", **kwargs: Any):
        return cls(
        success=True,
         output=output,
        **kwargs
    )
    
    def to_model_output(self)->str:
        if self.success:
            return self.output
        else:
            return f"error{self.error}\n\n Output:{self.output}"

@dataclass
class ToolConfirmation:
    tool_name:str
    params:dict[str,Any]
    description:str

    diff:FileDiff|None = None
    command:str|None = None
    is_dangerous:bool = False
    affected_paths:list[Path] = field(default_factory=list)

class Tool_kind(str,Enum):
    READ = "read"
    WRITE = 'write'
    SHELL ='shell'
    NETWORK = 'network'
    MEMORY = "memory"
    MCP = "mcp"

class Tool(ABC):
    name:str ="base_tool"
    description:str = "Base Tool"
    tool_kind:Tool_kind=Tool_kind.READ

    def __init__(self,config:Config):
        self.config = config

    @property
    def schema(self) -> dict[str,Any] | type['BaseModel']:
        raise NotImplementedError("tool must be define schema property or class attribute")
    
    @abc.abstractmethod
    async def execute(self,invocation:ToolInvocation)-> ToolResult:
        pass
    def validate_params(self,params:dict[str,Any]):
        schema=self.schema 
        if isinstance(schema,type)and issubclass(schema,BaseModel):
            try:
                schema(**params)
            except ValidationError as e :
                errors = []
                for error in e.errors():
                    field = '.'.join(str(x) for x in error.get('loc',[]))
                    msg = error.get('msg',"Validation Error")
                    errors.append(f"parameter :{field}:{msg}")
                return errors
            except Exception as e:
                return [str(e)]
    def is_mutating(self,param:dict[str,Any])-> bool:
        return self.tool_kind in (
        Tool_kind.WRITE,
        Tool_kind.SHELL,
        Tool_kind.NETWORK,
        Tool_kind.MEMORY,
        )
    async def get_confirmation(self,invocation:ToolInvocation)->ToolInvocation|None:
        if not self.is_mutating(invocation.params):
            return None
        return ToolConfirmation(
            tool_name=self.name,
            params=invocation.params,
            description=f"Execute{self.name}"
            
        )
    def to_open_ai_schema(self)->dict[str,Any]:
        schema=self.schema
        if isinstance(schema,type)and issubclass(schema,BaseModel):
            json_schema = model_json_schema(schema,mode='serialization')

            return {
                "name":self.name,
                'description':self.description,
                'parameters': {
                    'type':"object",
                    "properties":json_schema.get("properties",{}),
                    "required":json_schema.get("required",[])
                }
            }
        if isinstance(schema,dict):
            result = {"name":self.name,"description":self.description}
            if "parameters" in schema:
                result['parameters'] = schema['parameters']
            else :
                 result["parameters"] = schema
            return result
        else:
            raise ValueError(f"invalid schema type for tool{self.name} and {self.schema}")