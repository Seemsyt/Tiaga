from __future__ import annotations

from pathlib import Path
from typing import Any

from tiaga.config.config import Config
from tiaga.hooks.hook_system import HookSystem
from tiaga.tools_manager.buildin import get_all_builtin_tool
from tiaga.tools_manager.layers.catalog import ToolCatalog
from tiaga.tools_manager.layers.executor import ToolExecutor
from tiaga.tools_manager.subagent import SubagentTool, get_default_subagent_definition
from tiaga.tracing.trace import Trace
from tiaga.safety.approval import ApprovalManager


class ToolRegistry:
    """
    Compatibility facade:
    - catalog (data): registration and lookup
    - executor (control): invoke pipeline with approval/hooks/trace
    """

    def __init__(self, config: Config):
        self.config = config
        self.catalog = ToolCatalog(config=config)
        self.executor = ToolExecutor()

    @property
    def mcp_tools(self):
        return self.catalog.mcp_tools

    def register(self, tool):
        self.catalog.register(tool)

    def register_mcp(self, tool):
        self.catalog.register_mcp(tool)

    def unregister(self, name):
        return self.catalog.unregister(name)

    def get_tools(self):
        return self.catalog.get_tools()

    def get(self, name: str):
        return self.catalog.get(name)

    def get_schemas(self):
        return self.catalog.get_schemas()

    async def invoke(
        self,
        name: str,
        params: dict[str, Any],
        cwd: Path,
        approval: ApprovalManager | None = None,
        hook_system: HookSystem | None = None,
        trace_system: Trace | None = None,
    ):
        return await self.executor.invoke(
            name=name,
            params=params,
            cwd=cwd,
            catalog=self.catalog,
            approval=approval,
            hook_system=hook_system,
            trace_system=trace_system,
        )


def create_default_registry(config: Config) -> ToolRegistry:
    registry = ToolRegistry(config=config)
    for tool_cls in get_all_builtin_tool():
        registry.register(tool_cls(config))

    for sub_agent in get_default_subagent_definition():
        registry.register(SubagentTool(config, sub_agent))
    return registry
