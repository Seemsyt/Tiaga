from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from tiaga.hooks.hook_system import HookSystem
from tiaga.safety.approval import ApprovalContext, ApprovalDecision, ApprovalManager
from tiaga.tools_manager.base import ToolInvocation, ToolResult
from tiaga.tools_manager.layers.catalog import ToolCatalog
from tiaga.tracing.trace import Trace

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Control layer for validation, approval, and execution."""

    async def invoke(
        self,
        name: str,
        params: dict[str, Any],
        cwd: Path,
        catalog: ToolCatalog,
        approval: ApprovalManager | None = None,
        hook_system: HookSystem | None = None,
        trace_system: Trace | None = None,
    ) -> ToolResult:
        tool = catalog.get(name)
        if tool is None:
            result = ToolResult.error_result(f"tool does not exists {name}")
            if hook_system:
                await hook_system.trigger_after_tool(name, params, result)
            return result

        validation_error = tool.validate_params(params)
        if validation_error:
            result = ToolResult.error_result(f"Invalid parameters {validation_error}")
            if hook_system:
                await hook_system.trigger_after_tool(name, params, result)
            return result

        if trace_system:
            trace_system.trace_before_tool(name, params)
        if hook_system:
            await hook_system.trigger_before_tool(name, params)

        invocation = ToolInvocation(params, cwd)

        if approval:
            confirmation = await tool.get_confirmation(invocation)
            if confirmation:
                context = ApprovalContext(
                    tool_name=name,
                    params=params,
                    is_mutating=tool.is_mutating(params),
                    affected_paths=confirmation.affected_paths,
                    command=confirmation.command,
                    is_dangerous=confirmation.is_dangerous,
                )
                decision = await approval.check_approval(context=context)
                if decision == ApprovalDecision.REJECTED:
                    result = ToolResult.error_result("Operation was rejected by safety policy")
                    if hook_system:
                        await hook_system.trigger_after_tool(name, params, result)
                    return result
                if decision == ApprovalDecision.NEEDS_CONFIRMATION:
                    approved = approval.request_confirmation(confirmation)
                    if not approved:
                        result = ToolResult.error_result("Operation was rejected by safety policy")
                        if hook_system:
                            await hook_system.trigger_after_tool(name, params, result)
                        return result

        try:
            result = await tool.execute(invocation)
            if trace_system:
                trace_system.trace_after_tool(name, params, result)
            if hook_system:
                await hook_system.trigger_after_tool(name, params, result)
            return result
        except Exception as exc:
            logger.exception("Tool %s raised %s", name, exc)
            result = ToolResult.error_result(f"internal error {str(exc)} for {name}")
            if trace_system:
                trace_system.trace_after_tool(name, params, result)
            if hook_system:
                await hook_system.trigger_after_tool(name, params, result)
            return result
