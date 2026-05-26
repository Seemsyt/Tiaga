from __future__ import annotations

from tiaga.config.config import Config
from tiaga.tools_manager.layers.discovery import ToolDiscoveryManager
from tiaga.tools_manager.registry import ToolRegistry


class ToolDiscoveryManger(ToolDiscoveryManager):
    """
    Backward-compatible alias for old typo'd class name.
    """

    def __init__(self, config: Config, registry: ToolRegistry):
        super().__init__(config=config, catalog=registry.catalog)


__all__ = [
    "ToolDiscoveryManger",
    "ToolDiscoveryManager",
]
