from __future__ import annotations

import importlib
import logging
from typing import Type

from tiaga.tools_manager.base import Tool

logger = logging.getLogger(__name__)


# Keep imports lazy so a single missing optional dependency (e.g. `ddgs`) doesn't
# break *all* tools (including local-only ones like `write_file`).
_BUILTIN_TOOL_SPECS: list[tuple[str, str]] = [
    ("ReadFileTool", "tiaga.tools_manager.buildin.readfile"),
    ("WriteFileTool", "tiaga.tools_manager.buildin.writefile"),
    ("EditFileTool", "tiaga.tools_manager.buildin.editfile"),
    ("ShellTool", "tiaga.tools_manager.buildin.shell"),
    ("ListDir", "tiaga.tools_manager.buildin.listdir"),
    ("GrepTool", "tiaga.tools_manager.buildin.grep"),
    ("GlobTool", "tiaga.tools_manager.buildin.glob"),
    ("WebSearchTool", "tiaga.tools_manager.buildin.websearch"),
    ("WebFetchTool", "tiaga.tools_manager.buildin.webfetch"),
    ("YouTubeTranscriptTool", "tiaga.tools_manager.buildin.youtube_scrapping"),
    ("TodosTool", "tiaga.tools_manager.buildin.todo"),
    ("MemoryTool", "tiaga.tools_manager.buildin.memory"),
    ("ProjectGraphRefreshTool", "tiaga.tools_manager.buildin.project_graph_refresh"),
]


def _load_tool_class(class_name: str, module_path: str) -> Type[Tool] | None:
    try:
        module = importlib.import_module(module_path)
        obj = getattr(module, class_name)
        if isinstance(obj, type) and issubclass(obj, Tool):
            return obj
        logger.warning("Builtin tool %s in %s is not a Tool subclass", class_name, module_path)
        return None
    except Exception as exc:
        logger.debug("Skipping builtin tool %s (%s): %s", class_name, module_path, exc)
        return None


def get_all_builtin_tool() -> list[type[Tool]]:
    tools: list[type[Tool]] = []
    for class_name, module_path in _BUILTIN_TOOL_SPECS:
        tool_class = _load_tool_class(class_name, module_path)
        if tool_class is not None:
            tools.append(tool_class)
    return tools


_TOOL_SPEC_BY_NAME = {name: module for name, module in _BUILTIN_TOOL_SPECS}


def __getattr__(name: str):  # pragma: no cover
    module_path = _TOOL_SPEC_BY_NAME.get(name)
    if module_path:
        tool_class = _load_tool_class(name, module_path)
        if tool_class is None:
            raise AttributeError(name)
        return tool_class
    raise AttributeError(name)


__all__ = ["get_all_builtin_tool", *_TOOL_SPEC_BY_NAME.keys()]
