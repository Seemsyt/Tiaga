from tiaga.client.llm_client import LLM_client
from tiaga.config.config import Config


class Session:
    def __init__(self,config:Config):
        self.config = config
        self.client = LLM_client(config)
        