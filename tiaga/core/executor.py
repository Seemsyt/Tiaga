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
        )
        if not isinstance(result, ToolResult):
            result = ToolResult.error_result(
                f"tool {step.tool} returned invalid result type: {type(result).__name__}"
            )
        return ToolExecution(
            call_id=call_id,
            name=step.tool,
            args=args,
            result=result,
        )
