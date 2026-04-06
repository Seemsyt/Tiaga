import os
from pathlib import Path

from pydantic import BaseModel,Field

class ModelConfig(BaseModel):
    name:str = "stepfun/step-3.5-flash:free"
    temperature:float = Field(default=1,le=2.00,gt=0.00)
    context_window:int|None = 32000

class Config(BaseModel):
    model:ModelConfig = Field(default_factory=ModelConfig)
    cwd:Path = Field(default_factory=Path.cwd)

    max_turns:int = 100
    max_output_tokens:int = 50000

    developer_instruction:str|None = None
    user_instruction:str|None = None

    debug:bool  = True

    @property
    def api_key(self)-> str|None:
        return os.environ.get("API_KEY")
    @property
    def base_url(self)->str|None:
        return os.environ.get("BASE_URL")
    @property
    def model_name(self)->str|None:
        return self.model.name
    
    @model_name.setter
    def model_name(self,value)->str|None:
        self.model.name = value

    @property
    def temperature(self)->float:
        return self.model.temperature
    
    @temperature.setter
    def temprature(self,value)->str|None:
        self.model.temperature = value

    
    def validate(self):
        errors:list[str] = []
         
        if not self.api_key:
            errors.append('NO API key was found, set API_KEY in evronment variable')
        if not self.cwd.exists():
            errors.append(f"Working directory does not exists at {self.cwd}")
        return errors

    
