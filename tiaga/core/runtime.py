from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from tiaga.config.config import Config
from tiaga.context.compaction import ChatCompaction
from tiaga.context.manager import ContextManager
from tiaga.hooks.hook_system import HookSystem
from tiaga.safety.approval import ApprovalManager
from tiaga.tools_manager.registry import ToolRegistry
from tiaga.tracing.trace import Trace

if TYPE_CHECKING:
    from tiaga.client.llm_client import LLM_client


@dataclass(slots=True)
class RuntimeState:
    config: Config
    client: LLM_client
    context_manager: ContextManager
    tool_registry: ToolRegistry
    approval_manager: ApprovalManager
    hook_system: HookSystem
    trace_system: Trace
    chat_compactor: ChatCompaction
    project_graph_context: str | None = None
