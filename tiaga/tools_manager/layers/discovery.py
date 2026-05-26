from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any
import logging
from tiaga.config.config import Config
from tiaga.tools_manager.base import Tool
from tiaga.tools_manager.layers.catalog import ToolCatalog

logger = logging.getLogger(__name__)

class ToolDiscoveryManager:
    """Discovery layer for loading user-provided tools."""

    def __init__(self, config: Config, catalog: ToolCatalog):
        self.config = config
        self.catalog = catalog

    def _load_module(self, file_path: Path) -> Any:
        module_name = f"discovered_{file_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load spec from {file_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module=module)
        return module

    def _find_tool_classes(self, module: Any) -> list[type[Tool]]:
        tools: list[type[Tool]] = []
        for name in dir(module):
            obj = getattr(module, name)
            if (
                inspect.isclass(obj)
                and issubclass(obj, Tool)
                and obj is not Tool
                and obj.__module__ == module.__name__
            ):
                tools.append(obj)
        return tools

    def discover_from_directory(self, directory: Path) -> None:
        tool_dir = directory / ".seems-tiaga" / "tools"
        if not tool_dir.exists() or not tool_dir.is_dir():
            return
        for py_file in tool_dir.glob("*.py"):
            try:
                if py_file.name.startswith("__"):
                    continue
                module = self._load_module(py_file)
                for tool_class in self._find_tool_classes(module):
                    self.catalog.register(tool_class(self.config))
            except Exception as e:
                logger.exception("Failed to discover tool from %s",py_file)

    def discover_all(self) -> None:
        self.discover_from_directory(self.config.cwd)
