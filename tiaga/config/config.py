from __future__ import annotations
from enum import Enum
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel,Field, model_validator

class ModelConfig(BaseModel):
    name:str = "stepfun/step-3.5-flash:free"
    temperature:float = Field(default=1,le=2.00,gt=0.00)
    context_window:int|None = 160_000

class ShellEnvironmentPolicy(BaseModel):
    ignore_default_excludes:bool = False
    excludes_patterns: list[str] = Field(
    default_factory=lambda: ["*KEY*", "*TOKEN*", "*SECRET*"]
)
    set_vars:dict[str,str] = Field(default_factory=dict)


class MCPServersConfig(BaseModel):
    enabled:bool = True
    startup_timeout_seconds:float = 10 
    command:str|None =None
    args:list[str] = Field(default_factory=list)
    env:dict[str,str] = Field(default_factory=dict)
    cwd:Path|None = None

    url:str|None = None


    @classmethod
    @model_validator(mode="after")
    def validate_transport(self)->MCPServersConfig:
        has_command = self.command is not None
        has_url = self.url is not None

        if not has_command and not has_url:
            raise ValueError(f"MCP server should have either command (stdio) or url(hhtp/sse)")
        if has_url and has_command:
            raise ValueError(f"MCP server should not have both command (stdio) and url(hhtp/sse) ")
        
        return self


class ApprovalPolicy(str,Enum):
    ON_REQUEST = "on_request"
    ON_FAILURE = 'on_failure'
    AUTO = 'auto'
    AUTO_EDIT = 'auto_edit'
    NEVER="never"
    YOLO="yolo"

class HookTrigger(str, Enum):
    BEFORE_AGENT = "before_agent"
    AFTER_AGENT = "after_agent"
    BEFORE_TOOL = "before_tool"
    AFTER_TOOL = "after_tool"
    ON_ERROR = "on_error"


class HookConfig(BaseModel):
    name: str
    trigger: HookTrigger
    command: str | None = None  # python3 tests.py
    script: str | None = None  # *.sh
    timeout_sec: float = 30
    enabled: bool = True

    @model_validator(mode="after")
    def validate_hook(self) -> HookConfig:
        if not self.command and not self.script:
            raise ValueError("Hook must either have 'command' or 'script'")
        return self



class VoiceConfig(BaseModel):
    enabled: bool = False
    groq_api_key: str | None = None          
    openai_api_key: str | None = None        
    openai_tts_voice: str = "alloy"         
    openai_tts_model: str = "tts-1"         
    wake_word_model: str = "hey tiaga"     
    wake_word_threshold: float = 0.5         
    vad_silence_threshold: float = 0.8       
    vad_aggressiveness: int = 2              

class Config(BaseModel):
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    model:ModelConfig = Field(default_factory=ModelConfig)
    api_key_value:str|None = Field(default=None,alias="api_key")
    base_url_value:str|None = Field(default=None,alias="base_url")
    cwd:Path = Field(default_factory=Path.cwd)
    shell_environment:ShellEnvironmentPolicy = Field(default_factory=ShellEnvironmentPolicy)
    hooks_enabled:bool = False
    hooks:list[HookConfig] = Field(default_factory=HookConfig)
    approval:ApprovalPolicy = ApprovalPolicy.ON_REQUEST
    mcp_servers:dict[str,MCPServersConfig] = Field(...,default_factory=dict) 
    max_turns:int = 50
    max_output_tokens:int = 50000
    allowed_tools:list[str]|None = Field(
        default=None,
        description="If set, only these tools will be available for the agent",
    )

    developer_instruction:str|None = None
    user_instruction:str|None = None

    debug:bool  = True

    @property
    def api_key(self)-> str|None:
        return os.environ.get("API_KEY") or self.api_key_value

    @api_key.setter
    def api_key(self,value:str|None)->None:
        self.api_key_value = value
        if value is None:
            os.environ.pop("API_KEY",None)
        else:
            os.environ["API_KEY"] = value

    @property
    def base_url(self)->str|None:
        return os.environ.get("BASE_URL") or self.base_url_value

    @base_url.setter
    def base_url(self,value:str|None)->None:
        self.base_url_value = value
        if value is None:
            os.environ.pop("BASE_URL",None)
        else:
            os.environ["BASE_URL"] = value

    @property
    def model_name(self)->str|None:
        return self.model.name
    
    @model_name.setter
    def model_name(self,value:str)->None:
        self.model.name = value

    @property
    def temperature(self)->float:
        return self.model.temperature
    
    @temperature.setter
    def temperature(self,value:float)->None:
        self.model.temperature = value

    
    @property
    def groq_api_key(self) -> str | None:
        return os.environ.get("GROQ_API_KEY") or self.groq_api_key_value

    @property
    def openai_api_key(self) -> str | None:
        return os.environ.get("OPENAI_API_KEY") or self.openai_api_key_value


    def validate_config(self) -> list[str]:
        errors:list[str] = []
         
        if not self.api_key:
            errors.append('NO API key was found, set API_KEY in environment variable')
        if not self.cwd.exists():
            errors.append(f"Working directory does not exists at {self.cwd}")
        return errors
    def to_dict(self)->dict[str,Any]:
        return self.model_dump(mode='json')

    
