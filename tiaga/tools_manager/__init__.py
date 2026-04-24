"""
Public API for the tools subsystem.

Keep this module light: importing it is a dependency of low-level types like
`tiaga.tools_manager.base`, so eager imports here can easily create circular
imports (e.g. approval -> base -> tools_manager -> executor -> approval).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tiaga.tools_manager.discovery import ToolDiscoveryManager, ToolDiscoveryManger
    from tiaga.tools_manager.registry import ToolRegistry, create_default_registry

__all__ = ["ToolRegistry", "create_default_registry", "ToolDiscoveryManager", "ToolDiscoveryManger"]


def __getattr__(name: str) -> Any:  # pragma: no cover
    if name in {"ToolDiscoveryManager", "ToolDiscoveryManger"}:
        from tiaga.tools_manager.discovery import ToolDiscoveryManager, ToolDiscoveryManger

        return ToolDiscoveryManager if name == "ToolDiscoveryManager" else ToolDiscoveryManger
    if name in {"ToolRegistry", "create_default_registry"}:
        from tiaga.tools_manager.registry import ToolRegistry, create_default_registry

        return ToolRegistry if name == "ToolRegistry" else create_default_registry
    raise AttributeError(name)
