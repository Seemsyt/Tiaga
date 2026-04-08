from datetime import datetime
import json
import uuid

from tiaga.client.llm_client import LLM_client
from tiaga.config.config import Config 
from tiaga.config.loader import get_data_dir
from tiaga.context.manager import ContextManager
from tiaga.tools_manager.registry import create_default_registry





class Session:
    def __init__(self,config:Config):
        self.config = config
        self.client = LLM_client(config)
        self.tool_registry = create_default_registry(config)
        self.context_manager = ContextManager(config,memory=self._load_memory(),tools=self.tool_registry.get_tools())
        self.session_id = str(uuid.uuid4())
        self.created = datetime.now()
        self.updated = datetime.now()
        self._turn_count = 0 


    def _load_memory(self)->dict:
        data_dir = get_data_dir()
        data_dir.mkdir(parents=True,exist_ok=True)

        memory_path =  data_dir/"user_memory.json"

        if not memory_path.exists():
            return {"entries":{}}
        
        try:
            content = memory_path.read_text(encoding="utf-8")
            data =  json.loads(content)
            entries = data.get("entries")

            if entries:
                return None
            lines = ["user preferences and notes: "]
            for key,value in entries.items():
                lines.append(f"{key}: {value}")
            return '\n'.join(lines)
                
        except Exception as e :
            return None


    def increament_turn(self)->int:
        self._turn_count +=1
        self.updated = datetime.now()

        return self._turn_count
        
