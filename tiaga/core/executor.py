from __future__ import annotations

import json
from typing import Any

from tiaga.client.response import StreamEvent
from tiaga.core.runtime import RuntimeState
from tiaga.core.types import PlanStep, ToolExecution
from tiaga.tools_manager.base import ToolResult


class Executor:
    def __init__(self, runtime: RuntimeState):
        self.runtime = runtime

    async def stream_llm_for_step(self, step: PlanStep, user_message: str):
        payload = json.dumps(step.input or {}, ensure_ascii=False)
        instruction = (
            f"Execute plan step {step.step}: {step.task}\n"
            f"Plan input: {payload}\n"
            f"Original user request: {user_message}\n\n"
            "Provide the final user-facing response for this step."
        )
        messages = self.runtime.context_manager.get_messages() + [
            {"role": "user", "content": instruction}
        ]
        async for event in self.runtime.client.chat_completion(
            message=messages,
            tools=None,
            stream=True,
        ):
            yield event

    async def execute_tool_step(self, step: PlanStep) -> ToolExecution:
        call_id = f"plan-{step.step}-{step.tool}"
        args: dict[str, Any] = step.input if isinstance(step.input, dict) else {}
        result = await self.runtime.tool_registry.invoke(
            step.tool,
            args,
            self.runtime.config.cwd,
            self.runtime.approval_manager,
            self.runtime.hook_system,
            self.runtime.trace_system,
            parent_client=self.runtime.client,
        )
        if not isinstance(result, ToolResult):
            result = ToolResult.error_result(
                f"tool {step.tool} returned invalid result type: {type(result).__name__}"
            )

        # If the graph is refreshed mid-session, propagate it into runtime + system prompt
        # so subsequent turns/plans can use updated dependency context.
        if (
            step.tool == "project_graph_refresh"
            and result.success
            and isinstance(result.metadata, dict)
            and result.metadata.get("project_graph_context")
        ):
            context = str(result.metadata.get("project_graph_context") or "")
            self.runtime.project_graph_context = context
            if self.runtime.context_manager and context:
                header = "# Project Graph (Auto-generated)"
                base_prompt = self.runtime.context_manager.system_prompt or ""
                if header in base_prompt:
                    base_prompt = base_prompt.split(header, 1)[0].rstrip()
                self.runtime.context_manager.system_prompt = (base_prompt + "\n\n" + context).strip() + "\n"

        return ToolExecution(
            call_id=call_id,
            name=step.tool,
            args=args,
            result=result,
        )
