from datetime import datetime
import json
from typing import Any
import uuid

from tiaga.client.llm_client import LLM_client
from tiaga.config.config import Config 
from tiaga.config.loader import get_data_dir
from tiaga.core.planner import Planner
from tiaga.context.compaction import ChatCompaction
from tiaga.context.manager import ContextManager
from tiaga.hooks.hook_system import HookSystem
from tiaga.safety.approval import ApprovalManager
from tiaga.tools_manager.discovery import ToolDiscoveryManger
from tiaga.tools_manager.mcp.mcp_manager import MCPManager
from tiaga.tools_manager.registry import create_default_registry
from tiaga.tracing.trace import Trace

#session



class Session:
    def __init__(self,config:Config):
        self.config = config
        self.client = LLM_client(config)
        self.tool_registry = create_default_registry(config)
        self.tool_discovery_manager = ToolDiscoveryManger(self.config,self.tool_registry)
        self.mcp_manager = MCPManager(self.config)
        self.context_manager:ContextManager|None = None
        self.hook_system = HookSystem(self.config)
        self.trace_system = Trace()
        self.planner = Planner(self.client)
        self.approval_manager = ApprovalManager(self.config.approval,self.config.cwd)
        self.session_id = str(uuid.uuid4())
        self.chat_compactor = ChatCompaction(self.client)
        self.created = datetime.now()
        self.updated = datetime.now()
        self._turn_count = 0 
        


    @property
    def turn_count(self):
        return self._turn_count

    @turn_count.setter
    def turn_count(self,value):
        self._turn_count =  value
    async def initialize(self)->None:
        await self.mcp_manager.initialize()
        self.mcp_manager.register_tools(self.tool_registry)
        self.tool_discovery_manager.discover_all()

        self.context_manager = ContextManager(self.config,memory=self._load_memory(),tools=self.tool_registry.get_tools())

    

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

            if not entries:
                return None
            lines = ["user preferences and notes: "]
            for key,value in entries.items():
                lines.append(f"{key}: {value}")
            return '\n'.join(lines)
                
        except Exception as e :
            return None


    def increment_turn(self)->int:
        self._turn_count +=1
        self.updated = datetime.now()

        return self._turn_count
    
    def get_stats(self)->dict[str,Any]:
        return {
            "session_id":self.session_id,
            "created_at":self.created.isoformat(),
            "turn_count":self._turn_count,
            "messages":self.context_manager.len_msg,
            "total_usage":self.context_manager.total_usage,
            "tools_count":len(self.tool_registry.get_tools()),
            "mcp_servers":len(self.tool_registry.mcp_tools)
        }
    

    
