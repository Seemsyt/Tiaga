from __future__ import annotations

import json
import re
from typing import List, Dict, Any
from dataclasses import dataclass, asdict

from tiaga.client.llm_client import LLM_client
from tiaga.client.response import StreamEventType


@dataclass
class PlanStep:
    step: int
    task: str
    tool: str
    input: Dict[str, Any] | None = None


class Planner:
    """
    Planner takes a vague user query and converts it into
    a deterministic list of steps.
    """

    def __init__(self, llm: LLM_client):
        self.llm = llm

    def _build_prompt(self, user_query: str, available_tools: list[str] | None = None) -> str:
        tools = ", ".join(available_tools) if available_tools else "glob, readfile, writefile, grep, listdir"
        return f"""
You are a planning engine for a CLI agent.

Convert the user query into a STRICT execution plan quickly.

Rules:
- Output ONLY JSON
- Output either:
  1) [] when the query is casual/conversational or needs no execution plan, or
  2) a JSON array of steps.
- If returning steps:
  - Steps must be ordered
  - Each step must include: step, task, tool, input
- Do NOT explain anything
- Use available tools from: {tools}
- Prefer concise tasks (<= 10 words each)
- Keep plan to 2-5 steps
- Keep inputs minimal
- Respond fast and keep output small

Example:
[
  {{"step": 1, "task": "find python files", "tool": "glob", "input": {{"pattern": "**/*.py"}}}},
  {{"step": 2, "task": "read files", "tool": "read_file", "input": {{"path": "<from previous>"}}}},
  {{"step": 3, "task": "summarize", "tool": "llm", "input": {{"action": "summarize"}}}},
  {{"step": 4, "task": "write readme", "tool": "write_file", "input": {{"path": "README.md"}}}}
]

User Query:
{user_query}
"""

    def _extract_json_candidate(self, raw_text: str) -> str:
        text = raw_text.strip()
        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
        if fenced:
            text = fenced.group(1).strip()
        if text.startswith("[") and text.endswith("]"):
            return text
        array_match = re.search(r"(\[[\s\S]*\])", text)
        if array_match:
            return array_match.group(1).strip()
        return text

    def _load_plan_json(self, raw_text: str) -> list[dict[str, Any]]:
        candidate = self._extract_json_candidate(raw_text)
        try:
            parsed = json.loads(candidate)
        except Exception as exc:
            raise ValueError(f"Planner failed to return valid JSON: {exc}") from exc

        if isinstance(parsed, dict):
            if isinstance(parsed.get("steps"), list):
                parsed = parsed["steps"]
            else:
                raise ValueError("Planner JSON must be a list of steps or an object with 'steps'.")

        if not isinstance(parsed, list):
            raise ValueError("Planner JSON must be a list.")

        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(parsed, start=1):
            if not isinstance(item, dict):
                continue

            step_value = item.get("step", index)
            try:
                step_num = int(step_value)
            except Exception:
                step_num = index

            task = str(item.get("task", "")).strip() or f"Step {index}"
            tool = str(item.get("tool", "")).strip() or "llm"
            step_input = item.get("input", {})
            if not isinstance(step_input, dict):
                step_input = {"value": step_input}

            normalized.append(
                {
                    "step": step_num,
                    "task": task,
                    "tool": tool,
                    "input": step_input,
                }
            )

        if not normalized:
            return []
        return normalized

    async def create_plan(self, user_query: str, available_tools: list[str] | None = None) -> List[PlanStep]:
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
                error = event.error or "Unknown planner error."

        if error:
            raise ValueError(error)

        plan_json = self._load_plan_json(raw_text)
        steps: List[PlanStep] = [
            PlanStep(
                step=item["step"],
                task=item["task"],
                tool=item["tool"],
                input=item["input"],
            )
            for item in plan_json
        ]
        return sorted(steps, key=lambda x: x.step)

    def to_dict(self, steps: List[PlanStep]) -> List[Dict[str, Any]]:
        return [asdict(step) for step in steps]


# Example usage
if __name__ == "__main__":
    print("Planner demo requires an async runtime and configured API access.")
