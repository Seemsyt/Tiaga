from enum import Enum
import os
import sys
import json
from datetime import datetime
import uuid
from tiaga.config.loader import get_data_dir


class TraceType(str, Enum):
    TRACE_BEFORE_AGENT = "trace_before_agent"
    TRACE_AFTER_AGENT = "trace_after_agent"
    TRACE_BEFORE_TOOL = "trace_before_tool"
    TRACE_AFTER_TOOL = "trace_after_tool"
    TRACE_ON_ERROR = "trace_on_error"
    TRACE_RESPONSE_LATENCY = "trace_response_latency"


class Trace:

    @staticmethod
    def build_trace(
        trigger: TraceType,
        message: str = None,
        tool_name: str = None,
        error: str = None,
        **extra,
    ):
        log = {
            "timestamp": datetime.now().isoformat(),
            "trigger": trigger.value,
            "cwd": os.getcwd(),
            "tool_name": tool_name,
            "user_message": message,
            "error": error,
        }
        if extra:
            log.update(extra)
        return log

    @staticmethod
    def write_trace(log_data: dict):
        hook_id = str(uuid.uuid4())

        log_path = get_data_dir() / "logs" / "traces.log"
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        with open(log_path, "a") as f:
            f.write(f"[HOOK] hook_id:{hook_id}, {json.dumps(log_data, default=str)}\n")

    # ---- Trace Hooks ----

    @staticmethod
    def trace_before_agent(user_message: str):
        log = Trace.build_trace(
            trigger=TraceType.TRACE_BEFORE_AGENT,
            message=user_message
        )
        Trace.write_trace(log)

    @staticmethod
    def trace_after_agent(user_message: str, final_response: str, latency: float = None, turn_count: int = None, token_usage: dict = None):
        log = Trace.build_trace(
            trigger=TraceType.TRACE_AFTER_AGENT,
            message=user_message,
            final_response=final_response,
            latency_seconds=latency,
            turn_count=turn_count,
            token_usage=token_usage,
        )
        Trace.write_trace(log)

    @staticmethod
    def trace_before_tool(tool_name: str, params: str, call_id: str = None):
        log = Trace.build_trace(
            trigger=TraceType.TRACE_BEFORE_TOOL,
            tool_name=tool_name,
            params=params,
            call_id=call_id,
        )
        Trace.write_trace(log)

    @staticmethod
    def trace_after_tool(tool_name: str, params: str, result: str, success: bool = True, error: str = None, execution_time: float = None, call_id: str = None):
        log = Trace.build_trace(
            trigger=TraceType.TRACE_AFTER_TOOL,
            tool_name=tool_name,
            params=params,
            result=result,
            success=success,
            error=error,
            execution_time_seconds=execution_time,
            call_id=call_id,
        )
        Trace.write_trace(log)

    @staticmethod
    def trace_on_error(error: str, user_message: str = None, tool_name: str = None):
        log = Trace.build_trace(
            trigger=TraceType.TRACE_ON_ERROR,
            message=user_message,
            tool_name=tool_name,
            error=error
        )
        Trace.write_trace(log)

    @staticmethod
    def trace_response_latency(latency: float, turn_count: int = None, token_usage: dict = None, success: bool = True):
        """Track response latency metrics with optional turn and token data."""
        log = Trace.build_trace(
            trigger=TraceType.TRACE_RESPONSE_LATENCY,
            latency_seconds=latency,
            turn_count=turn_count,
            token_usage=token_usage,
            success=success,
        )
        Trace.write_trace(log)

    # optional main trigger
    @staticmethod
    def main(trigger: TraceType, **kwargs):
        log = Trace.build_trace(trigger=trigger, **kwargs)
        Trace.write_trace(log)

