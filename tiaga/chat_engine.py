"""
Chat Engine - Pure business logic, no UI dependencies.

This module handles:
- LangGraph workflow compilation
- Streaming chat events
- Tool execution
- Checkpoint persistence
"""

import os
import sqlite3
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from .graph import graph as compiled_graph
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

DB_PATH = os.getenv("TIAGA_DB_PATH", str(Path.home() / ".tiaga" / "chat_history.db"))
DEFAULT_RECURSION_LIMIT = 100


class ChatEngine:
    """Pure chat engine - no UI dependencies."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(Path(db_path).parent, exist_ok=True)

    def get_checkpointer(self):
        """Get async checkpointer context manager."""
        return AsyncSqliteSaver.from_conn_string(self.db_path)

    def _normalize_thread_id(self, thread_id: str) -> str:
        """Ensure thread IDs are always safe non-empty strings."""
        thread_id = (thread_id or "").strip()
        return thread_id or "session"

    def _config(self, thread_id: str) -> dict:
        return {
            "configurable": {"thread_id": self._normalize_thread_id(thread_id)},
            "recursion_limit": DEFAULT_RECURSION_LIMIT,
        }

    def _compile_graph(self, checkpointer):
        return compiled_graph.compile(checkpointer=checkpointer)

    def _is_visible_message(self, message: BaseMessage) -> bool:
        if isinstance(message, HumanMessage):
            return True
        if isinstance(message, AIMessage):
            if getattr(message, "tool_calls", None):
                return False
            content = message.content
            if isinstance(content, str):
                return bool(content.strip())
            if isinstance(content, list):
                return any(str(part).strip() for part in content)
        return False

    async def stream_events(self, message: str, thread_id: str):
        """
        Stream events from the agent.

        Yields:
            dict: Event data with keys: type, name, data, run_id
        """
        thread_id = self._normalize_thread_id(thread_id)
        async with self.get_checkpointer() as checkpointer:
            graph = self._compile_graph(checkpointer)
            config = self._config(thread_id)
            input_ = {"messages": [HumanMessage(content=message)]}

            async for event in graph.astream_events(
                input=input_,
                config=config,
                version="v2"
            ):
                yield event

    async def stream_turn(self, message: str, thread_id: str):
        """
        Stream one user-visible turn while suppressing duplicate assistant reruns.

        LangGraph/model retries can sometimes emit a second chat-model stream for
        the same user input. We allow a fresh assistant stream after tool activity,
        but otherwise ignore later duplicate runs in the same turn.
        """
        active_run_id = None
        assistant_started = False
        tool_activity_since_last_response = False

        async for event in self.stream_events(message, thread_id):
            kind = event.get("event")

            if kind in {"on_tool_start", "on_tool_end"}:
                tool_activity_since_last_response = True
                active_run_id = None
                assistant_started = False
                yield event
                continue

            if kind != "on_chat_model_stream":
                yield event
                continue

            chunk = event.get("data", {}).get("chunk")
            if not chunk or not getattr(chunk, "content", None):
                continue

            run_id = event.get("run_id")
            if active_run_id is None:
                active_run_id = run_id
            elif run_id != active_run_id:
                if assistant_started and not tool_activity_since_last_response:
                    continue
                active_run_id = run_id
                assistant_started = False

            assistant_started = True
            tool_activity_since_last_response = False
            yield event

    async def get_history(self, thread_id: str) -> list[BaseMessage]:
        """Load the latest stored messages for a thread."""
        thread_id = self._normalize_thread_id(thread_id)
        async with self.get_checkpointer() as checkpointer:
            graph = self._compile_graph(checkpointer)
            config = self._config(thread_id)
            state = await graph.aget_state(config)
            if not state or not getattr(state, "values", None):
                return []
            messages = state.values.get("messages", [])
            return [msg for msg in messages if isinstance(msg, BaseMessage)]

    async def get_visible_history(self, thread_id: str) -> list[BaseMessage]:
        """Return only user/assistant conversational messages for UI display."""
        messages = await self.get_history(thread_id)
        return [message for message in messages if self._is_visible_message(message)]

    async def list_sessions(self) -> list[str]:
        """List all session thread IDs."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id"
                ).fetchall()
            return [row[0] for row in rows if row and row[0]]
        except Exception:
            return []

    async def create_session(self, name: str) -> str:
        """Create a new session with given name (slugified)."""
        return self._normalize_thread_id(name)


# Singleton instance (created per thread_id)
_engine_cache = {}

def get_engine(db_path: str = DB_PATH) -> ChatEngine:
    """Get or create engine instance."""
    if db_path not in _engine_cache:
        _engine_cache[db_path] = ChatEngine(db_path)
    return _engine_cache[db_path]
