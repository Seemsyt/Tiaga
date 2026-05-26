from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tiaga.client.response import TokenUsage, ToolCall
from tiaga.tools_manager.base import ToolResult


@dataclass(slots=True)
class PlanStep:
    step: int
    task: str
    tool: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ModelTurn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    started_tool_calls: set[str] = field(default_factory=set)
    usage: TokenUsage | None = None
    error: str | None = None


@dataclass(slots=True)
class ToolExecution:
    call_id: str
    name: str
    args: dict[str, Any]
    result: ToolResult
