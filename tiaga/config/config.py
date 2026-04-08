import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel,Field

class ModelConfig(BaseModel):
    name:str = "stepfun/step-3.5-flash:free"
    temperature:float = Field(default=1,le=2.00,gt=0.00)
    context_window:int|None = 32000

class ShellEnvronmentPolicy(BaseModel):
    ignore_default_exludes:bool = False
    excludes_patterns: list[str] = Field(
    default_factory=lambda: ["*KEY*", "*TOKEN*", "*SECRET*"]
)
    set_vars:dict[str,str] = Field(default_factory=dict)


class Config(BaseModel):
    model:ModelConfig = Field(default_factory=ModelConfig)
    api_key_value:str|None = Field(default=None,alias="api_key")
    base_url_value:str|None = Field(default=None,alias="base_url")
    cwd:Path = Field(default_factory=Path.cwd)
    shell_environment:ShellEnvronmentPolicy = Field(default_factory=ShellEnvronmentPolicy)

    max_turns:int = 100
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
    def temprature(self,value:float)->None:
        self.model.temperature = value

    
    def validate_config(self) -> list[str]:
        errors:list[str] = []
         
        if not self.api_key:
            errors.append('NO API key was found, set API_KEY in environment variable')
        if not self.cwd.exists():
            errors.append(f"Working directory does not exists at {self.cwd}")
        return errors
    def to_dict(self)->dict[str,Any]:
        return self.model_dump(mode='json')

    
