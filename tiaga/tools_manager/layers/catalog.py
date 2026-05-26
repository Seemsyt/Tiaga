from __future__ import annotations

import logging

from tiaga.config.config import Config
from tiaga.tools_manager.base import Tool

logger = logging.getLogger(__name__)


class ToolCatalog:
    """Data layer for tool registration and lookup."""

    def __init__(self, config: Config):
        self.config = config
        self._tools: dict[str, Tool] = {}
        self._mcp_tools: dict[str, Tool] = {}

    @property
    def mcp_tools(self) -> list[Tool]:
        return list(self._mcp_tools.values())

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            logger.warning("Overwriting existing tool %s", tool.name)
        self._tools[tool.name] = tool

    def register_mcp(self, tool: Tool) -> None:
        self._mcp_tools[tool.name] = tool

    def unregister(self, name: str) -> bool:
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get(self, name: str) -> Tool | None:
        if self.config.allowed_tools and name not in set(self.config.allowed_tools):
            return None
        if name in self._tools:
            return self._tools.get(name)
        return self._mcp_tools.get(name)

    def get_tools(self) -> list[Tool]:
        tools = [*self._tools.values(), *self._mcp_tools.values()]
        if self.config.allowed_tools:
            allowed = set(self.config.allowed_tools)
            tools = [tool for tool in tools if tool.name in allowed]
        return tools

    def get_schemas(self) -> list[dict]:
        return [tool.to_open_ai_schema() for tool in self.get_tools()]
