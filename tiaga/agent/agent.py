from __future__ import annotations

from typing import Callable

from tiaga.agent.events import AgentEventType
from tiaga.agent.session import Session
from tiaga.config.config import Config
from tiaga.core.orchestrator import Orchestrator
from tiaga.core.runtime import RuntimeState
from tiaga.tools_manager.base import ToolConfirmation


class Agent:
    def __init__(
        self,
        config: Config,
        confirmation_callback: Callable[[ToolConfirmation], bool] | None = None,
    ):
        self.config = config
        self.session: Session | None = Session(self.config)
        self.session.approval_manager.confirmation_callback = confirmation_callback
        self.orchestrator: Orchestrator | None = None

    async def run(self, message: str):
        if not self.session or not self.orchestrator:
            return
        self.session.trace_system.trace_before_agent(user_message=message)
        await self.session.hook_system.trigger_before_agent(message)

        final_response = ""
        async for event in self.orchestrator.run(message):
            if event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content", "") or final_response
            elif event.type == AgentEventType.AGENT_END:
                final_response = event.data.get("response", "") or final_response
            yield event

        self.session.trace_system.trace_after_agent(message, final_response)
        await self.session.hook_system.trigger_after_agent(message, final_response)

    async def __aenter__(self):
        await self.session.initialize()
        runtime = RuntimeState(
            config=self.session.config,
            client=self.session.client,
            context_manager=self.session.context_manager,
            tool_registry=self.session.tool_registry,
            approval_manager=self.session.approval_manager,
            hook_system=self.session.hook_system,
            trace_system=self.session.trace_system,
            chat_compactor=self.session.chat_compactor,
        )
        self.orchestrator = Orchestrator(runtime=runtime, planner=self.session.planner)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.session and self.session.client:
            await self.session.client.close_client()
            await self.session.mcp_manager.shutdown()
            self.session.client = None
            self.session = None
