from __future__ import annotations

import json
from typing import AsyncGenerator

from tiaga.agent.events import AgentEvent
from tiaga.client.response import StreamEventType
from tiaga.core.executor import Executor
from tiaga.core.planner import Planner
from tiaga.core.runtime import RuntimeState
from tiaga.core.types import PlanStep


class Orchestrator:
    def __init__(self, runtime: RuntimeState, planner: Planner):
        self.runtime = runtime
        self.executor = Executor(runtime)
        self.planner = planner

    def _normalize_plan(self, plan: list[PlanStep], tools: set[str]) -> list[PlanStep]:
        valid_tool_steps: list[PlanStep] = []
        llm_step: PlanStep | None = None

        for step in sorted(plan, key=lambda item: item.step):
            tool = (step.tool or "").strip()
            if tool == "llm":
                if llm_step is None:
                    llm_step = step
                continue
            if tool in tools:
                valid_tool_steps.append(step)

        if llm_step is None:
            llm_step = PlanStep(
                step=len(valid_tool_steps) + 1,
                task="Generate final answer for user",
                tool="llm",
                input={},
            )

        normalized: list[PlanStep] = []
        for index, step in enumerate(valid_tool_steps + [llm_step], start=1):
            normalized.append(
                PlanStep(
                    step=index,
                    task=step.task,
                    tool=step.tool,
                    input=step.input or {},
                )
            )
        return normalized

    async def run(self, message: str) -> AsyncGenerator[AgentEvent, None]:
        yield AgentEvent.agent_start(messages=message)
        self.runtime.context_manager.add_user_message(message)

        tool_names = [tool.name for tool in self.runtime.tool_registry.get_tools()]
        planned_steps = await self.planner.create_plan(message, tool_names + ["llm"])
        plan = self._normalize_plan(planned_steps, set(tool_names))
        plan_items = [
            {"step": step.step, "task": step.task, "tool": step.tool, "input": step.input}
            for step in plan
        ]
        yield AgentEvent.plan(plan_items)

        final_response = ""
        for step in plan:
            if self.runtime.context_manager.need_compression():
                summary, usage = await self.runtime.chat_compactor.compress(self.runtime.context_manager)
                if summary:
                    self.runtime.context_manager.repplace_with_summary(summary=summary)
                    self.runtime.context_manager.latest_usage(usage)
                    self.runtime.context_manager.update_usage(usage)

            if step.tool == "llm":
                response_text = ""
                usage = None
                error = None
                async for event in self.executor.stream_llm_for_step(step=step, user_message=message):
                    if event.type == StreamEventType.TEXT_DELTA and event.text_delta:
                        content = event.text_delta.content or ""
                        response_text += content
                        yield AgentEvent.text_delta(content=content)
                    elif event.type == StreamEventType.MESSAGE_COMPLETE:
                        usage = event.usage
                    elif event.type == StreamEventType.ERROR:
                        error = event.error or "Unknown model error."

                if error:
                    final_response = error
                    yield AgentEvent.agent_error(error=error)
                    break

                self.runtime.context_manager.add_assistant_message(response_text)
                if usage:
                    self.runtime.context_manager.latest_usage(usage)
                    self.runtime.context_manager.update_usage(usage)
                self.runtime.context_manager.pruning_tool_outputs()
                final_response = response_text
                yield AgentEvent.text_complete(response_text)
                continue

            tool_call = {
                "id": f"plan-{step.step}-{step.tool}",
                "type": "function",
                "function": {
                    "name": step.tool,
                    "arguments": json.dumps(step.input or {}),
                },
            }
            self.runtime.context_manager.add_assistant_message("", tool_calls=[tool_call])
            yield AgentEvent.tool_call_start(
                call_id=tool_call["id"],
                name=step.tool,
                arguments=step.input or {},
            )

            executed = await self.executor.execute_tool_step(step)
            yield AgentEvent.tool_call_complete(executed.call_id, executed.name, executed.result)
            self.runtime.context_manager.add_tool_message(
                executed.call_id,
                executed.result.to_model_output(),
            )
            self.runtime.context_manager.pruning_tool_outputs()

        yield AgentEvent.agent_end(response=final_response)
