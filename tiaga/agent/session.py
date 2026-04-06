from datetime import datetime
import uuid

from tiaga.client.llm_client import LLM_client
from tiaga.config.config import Config
from tiaga.context.manager import ContextManager
from tiaga.tools_manager.registry import create_default_registry


class Session:
    def __init__(self,config:Config):
        self.config = config
        self.client = LLM_client(config)
        self.tool_registry = create_default_registry(config)
        self.context_manager = ContextManager(config)
        self.session_id = str(uuid.uuid4())
        self.created = datetime.now()
        self.updated = datetime.now()
        self._turn_count = 0 

    def increament_turn(self)->int:
        self._turn_count +=1
        self.updated = datetime.now()

        return self._turn_count
        
