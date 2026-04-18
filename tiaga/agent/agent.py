from __future__ import annotations
import json
from pathlib import Path
from typing import AsyncGenerator, Callable
from tiaga.client.llm_client import LLM_client
from tiaga.client.response import StreamEventType, TokenUsage, ToolCall, ToolResultMessage  # Fix typo: reaponse -> response
from tiaga.agent.session import Session
from tiaga.context.prompts import create_loop_breaker_prompt
from tiaga.tools_manager.registry import create_default_registry
from tiaga.tools_manager.base import ToolConfirmation, ToolResult
from tiaga.config.config import Config
from .events import AgentEvent, AgentEventType



class Agent:
    def __init__(self, config: Config, confirmation_callback: Callable[[ToolConfirmation], bool] | None = None,):
     
  
        self.config = config
        self.session:Session|None = Session(self.config)
        self.session.approval_manager.confirmation_callback = confirmation_callback

    async def run(self, message: str):
        self.session.trace_system.trace_before_agent(user_message=message)
        await self.session.hook_system.trigger_before_agent(message)
        yield AgentEvent.agent_start(messages=message)
        self.session.context_manager.add_user_message(message)
        final_response = None

        async for event in self._agentic_loop():
            yield event
            if event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content", "")
        self.session.trace_system.trace_after_agent(message,final_response)
        await self.session.hook_system.trigger_after_agent(message,final_response)

        yield AgentEvent.agent_end(response=final_response)

    async def _agentic_loop(self) -> AsyncGenerator[AgentEvent, None]:
        max_turn = self.config.max_turns
        consecutive_tool_only_turns = 0
        executed_tools = False
        summary_retry_count = 0
        max_summary_retries = 2

        for turn_num in range(max_turn):
            self.session.increament_turn()
            tool_schema = self.session.tool_registry.get_schemas()
            response_text = ""
            tools_calls: list[ToolCall] = []
            started_tool_calls: set[str] = set()
            usage: TokenUsage | None = None

            if self.session.context_manager.need_compression():
                summary, usage = await self.session.chat_compactor.compress(self.session.context_manager)
                if summary:
                    self.session.context_manager.repplace_with_summary(summary=summary)
                    self.session.context_manager.latest_usage(usage)
                    self.session.context_manager.update_usage(usage)

            async for event in self.session.client.chat_completion(
                message=self.session.context_manager.get_messages(),
                tools=tool_schema if tool_schema else None,
                stream=True,
            ):
                if event.type == StreamEventType.TEXT_DELTA and event.text_delta:
                    content = event.text_delta.content
                    response_text += content
                    yield AgentEvent.text_delta(content=content)

                elif event.type == StreamEventType.TOOL_CALL_COMPLETE:
                    if event.tool_call:
                        tools_calls.append(event.tool_call)
                elif event.type == StreamEventType.TOOL_CALL_START:
                    if event.tool_call_delta:
                        call_id = event.tool_call_delta.call_id or f"pending_{len(started_tool_calls)}"
                        started_tool_calls.add(call_id)
                        yield AgentEvent.tool_call_start(
                            call_id=call_id,
                            name=event.tool_call_delta.name or "unknown",
                            arguments={},
                        )

                elif event.type == StreamEventType.MESSAGE_COMPLETE:
                    usage = event.usage

                elif event.type == StreamEventType.ERROR:

                    yield AgentEvent.agent_error(
                        detail=None,
                        error=event.error or "Unknown error occurred.",
                    )

            # Build assistant tool call dicts
            assistant_tool_calls: list[dict[str, object]] = []
            for tool_call in tools_calls:
                assistant_tool_calls.append({
                    "id": tool_call.call_id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name or "",
                        "arguments": json.dumps(tool_call.arguments or {}),
                    },
                })
            has_response_text = bool(response_text and response_text.strip())

            # Always save assistant message before any return
            if has_response_text or assistant_tool_calls:
                self.session.context_manager.add_assistant_message(
                    response_text or "",
                    tool_calls=assistant_tool_calls,
                )

            # Clean exit: LLM responded with text and no tool calls
            if has_response_text and not tools_calls:
                if usage:
                    self.session.context_manager.latest_usage(usage)
                    self.session.context_manager.update_usage(usage)
                self.session.context_manager.pruning_tool_outputs()
                yield AgentEvent.text_complete(response_text)
                return

            # Track consecutive tool-only turns (no text response)
            if tools_calls and not has_response_text:
                consecutive_tool_only_turns += 1
            else:
                consecutive_tool_only_turns = 0

            if consecutive_tool_only_turns >= 5:
                self.session.context_manager.add_user_message(
                    "You have been calling tools for several turns without producing a response. "
                    "Stop now, summarize your findings, and give your final answer."
                )
                consecutive_tool_only_turns = 0

            if has_response_text:
                yield AgentEvent.text_complete(response_text)
                self.session.loop_detector.record_actions("response", text=response_text)
                summary_retry_count = 0

            if not tools_calls:
                if not has_response_text and executed_tools and summary_retry_count < max_summary_retries:
                    # Guard against silent completion after tool execution.
                    self.session.context_manager.add_user_message(
                        "Provide your final response to the user based on the tool results above. "
                        "Do not call more tools unless absolutely necessary. "
                        "Give a concise, user-facing answer now."
                    )
                    summary_retry_count += 1
                    continue
                if not has_response_text and executed_tools:
                    fallback = (
                        "I completed tool execution, but I could not generate the final summary text. "
                        "Please ask me to summarize again and I will provide it directly."
                    )
                    yield AgentEvent.text_complete(fallback)
                    if usage:
                        self.session.context_manager.latest_usage(usage)
                        self.session.context_manager.update_usage(usage)
                    self.session.context_manager.pruning_tool_outputs()
                    return
                if usage:
                    self.session.context_manager.latest_usage(usage)
                    self.session.context_manager.update_usage(usage)
                self.session.context_manager.pruning_tool_outputs()
                return

            # Execute tool calls
            tool_call_results: list[ToolResultMessage] = []
            for tool_call in tools_calls:
                call_id = tool_call.call_id or f"pending_{len(started_tool_calls)}"
                started_tool_calls.add(call_id)
                # Re-emit start with parsed arguments so UI can show params
                # before execution (and update an already-mounted running card).
                yield AgentEvent.tool_call_start(
                    call_id=call_id,
                    name=tool_call.name,
                    arguments=tool_call.arguments or {},
                )
                self.session.loop_detector.record_actions("tool_call", tool_name=tool_call.name, args=tool_call.arguments)
                result = await self.session.tool_registry.invoke(
                    tool_call.name,
                    tool_call.arguments,
                    self.config.cwd,
                    self.session.approval_manager,
                    self.session.hook_system,
                    self.session.trace_system,
                )

                if not isinstance(result, ToolResult):
                    result = ToolResult.error_result(
                        f"tool {tool_call.name} returned invalid result type: {type(result).__name__}"
                    )

                yield AgentEvent.tool_call_complete(call_id, tool_call.name, result)
                executed_tools = True
                tool_call_results.append(ToolResultMessage(
                    tool_call_id=call_id,
                    content=result.to_model_output(),
                    is_error=not result.success,
                ))

            for tool_result in tool_call_results:
                self.session.context_manager.add_tool_message(
                    tool_result.tool_call_id,
                    tool_result.content,
                )

            loop_detection_error = self.session.loop_detector.check_for_loop()
            if loop_detection_error:
                loop_prompt = create_loop_breaker_prompt(loop_detection_error)
                self.session.context_manager.add_user_message(loop_prompt)

            if usage:
                self.session.context_manager.latest_usage(usage)
                self.session.context_manager.update_usage(usage)
            self.session.context_manager.pruning_tool_outputs()

        yield AgentEvent.agent_error(f"Maximum turns ({max_turn}) reached")
               

    async def __aenter__(self):
        await self.session.initialize()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.session and self.session.client:
            await self.session.client.close_client()
            await self.session.mcp_manager.Shoutdown()
            self.session.client = None
            self.session = None
