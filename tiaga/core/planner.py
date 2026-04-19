from __future__ import annotations

import json
import re

from tiaga.client.llm_client import LLM_client
from tiaga.client.response import StreamEventType
from tiaga.core.types import PlanStep


class Planner:
    def __init__(self, llm: LLM_client):
        self.llm = llm

    def _build_prompt(self, user_query: str, available_tools: list[str]) -> str:
        tool_str = ", ".join(available_tools) if available_tools else "none"
        return f"""
You are a planning engine for an agent runtime.

Return ONLY JSON.

Allowed outputs:
1) []  (if no plan is needed)
2) [{{"step":1,"task":"...","tool":"...","input":{{}}}}]

Rules:
- Use only tools from: {tool_str}
- Keep 2 to 5 steps
- Keep each task short
- No explanations, no markdown

User:
{user_query}
"""

    def _extract_json_candidate(self, raw_text: str) -> str:
        text = raw_text.strip()
        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
        if fenced:
            text = fenced.group(1).strip()
        if text.startswith("[") and text.endswith("]"):
            return text
        match = re.search(r"(\[[\s\S]*\])", text)
        if match:
            return match.group(1).strip()
        return text

    def _normalize_plan(self, payload: object) -> list[PlanStep]:
        if not isinstance(payload, list):
            return []
        normalized: list[PlanStep] = []
        for index, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                continue
            step_raw = item.get("step", index)
            try:
                step_num = int(step_raw)
            except Exception:
                step_num = index
            task = str(item.get("task", "")).strip() or f"Step {index}"
            tool = str(item.get("tool", "")).strip()
            step_input = item.get("input", {})
            if not isinstance(step_input, dict):
                step_input = {"value": step_input}
            if not tool:
                continue
            normalized.append(
                PlanStep(
                    step=step_num,
                    task=task,
                    tool=tool,
                    input=step_input,
                )
            )
        return sorted(normalized, key=lambda step: step.step)

    async def create_plan(self, user_query: str, available_tools: list[str]) -> list[PlanStep]:
        prompt = self._build_prompt(user_query, available_tools)
        raw_text = ""
        error = None

        async for event in self.llm.chat_completion(
            message=[{"role": "user", "content": prompt}],
            tools=None,
            stream=False,
        ):
            if event.type == StreamEventType.MESSAGE_COMPLETE and event.text_delta:
                raw_text = event.text_delta.content or ""
            elif event.type == StreamEventType.ERROR:
                error = event.error or "Planner failed."

        if error:
            return []

        try:
            data = json.loads(self._extract_json_candidate(raw_text))
        except Exception:
            return []
        return self._normalize_plan(data)
