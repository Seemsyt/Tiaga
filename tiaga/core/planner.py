from __future__ import annotations

import json
import re
from typing import Any

from tiaga.client.llm_client import LLM_client
from tiaga.client.response import StreamEventType
from tiaga.core.types import PlanStep
from pydantic import BaseModel, ValidationError


class Planner:
    def __init__(self, llm: LLM_client):
        self.llm = llm

    def _format_tool_schemas(self, tool_schemas: list[dict[str, Any]]) -> str:
        """Format tool schemas for the LLM prompt."""
        if not tool_schemas:
            return ""
        
        formatted = "\n\nTool Schemas:\n"
        for schema in tool_schemas:
            name = schema.get("name", "unknown")
            description = schema.get("description", "")
            parameters = schema.get("parameters", {})
            
            formatted += f"\n{name}:\n"
            if description:
                formatted += f"  Description: {description}\n"
            
            params_obj = parameters.get("parameters", {})
            required = parameters.get("required", [])
            props = parameters.get("properties", {})
            
            if props:
                formatted += "  Parameters:\n"
                for param_name, param_spec in props.items():
                    param_type = param_spec.get("type", "any")
                    param_desc = param_spec.get("description", "")
                    is_required = param_name in required
                    req_str = "required" if is_required else "optional"
                    formatted += f"    - {param_name} ({param_type}, {req_str})"
                    if param_desc:
                        formatted += f": {param_desc}"
                    formatted += "\n"
        
        return formatted

    def _build_prompt(
        self, 
        user_query: str, 
        available_tools: list[str],
        tool_schemas: list[dict[str, Any]] | None = None,
        validation_errors: list[str] | None = None,
        project_context: str | None = None,
    ) -> str:
        tool_str = ", ".join(available_tools) if available_tools else "none"
        
        schemas_section = ""
        if tool_schemas:
            schemas_section = self._format_tool_schemas(tool_schemas)
        
        error_feedback = ""
        if validation_errors:
            error_feedback = "\nPrevious plan had validation errors. Please fix:\n"
            for error in validation_errors:
                error_feedback += f"  ❌ {error}\n"
            error_feedback += "\nAttempt again with corrected parameters.\n"

        project_section = ""
        if project_context:
            # Keep it as plain text so the JSON-only instruction remains unambiguous.
            project_section = f"\n\nProject context (dependency graph):\n{project_context.strip()}\n"
        
        return f"""
You are a planning engine for an agent runtime.

Return ONLY JSON.

Allowed outputs:
1) []  (if no plan is needed)
2) [{{"step":1,"task":"...","tool":"...","input":{{}}}}]

Rules:
- Use only tools from: {tool_str}
- For each tool, provide ALL required parameters in input
- Check the tool schemas below for parameter names and types
- Keep 2 to 5 steps
- Keep each task short
- No explanations, no markdown{schemas_section}{error_feedback}{project_section}

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

    def validate_plan(
        self, 
        plan: list[PlanStep], 
        tool_schemas: dict[str, dict[str, Any]]
    ) -> list[str]:
        """
        Validate a plan against tool schemas.
        Returns list of validation errors (empty if valid).
        """
        errors = []
        for step in plan:
            tool_name = step.tool
            if tool_name == "llm":
                # LLM steps don't need parameter validation
                continue
            
            if tool_name not in tool_schemas:
                errors.append(f"Step {step.step}: Tool '{tool_name}' not available")
                continue
            
            schema = tool_schemas[tool_name]
            params = schema.get("parameters", {})
            required_fields = params.get("required", [])
            
            # Check required fields
            for required_field in required_fields:
                if required_field not in step.input:
                    errors.append(
                        f"Step {step.step} ({tool_name}): Missing required parameter '{required_field}'"
                    )
        
        return errors

    async def create_plan(
        self, 
        user_query: str, 
        available_tools: list[str],
        tool_schemas: list[dict[str, Any]] | None = None,
        max_retries: int = 2,
        project_context: str | None = None,
    ) -> list[PlanStep]:
        """
        Create a plan with optional schema validation and retry logic.
        
        Args:
            user_query: The user's request
            available_tools: List of tool names
            tool_schemas: List of tool schema dicts (from registry.get_schemas())
            max_retries: Max number of retries if validation fails
        
        Returns:
            List of PlanStep objects
        """
        # Build schema lookup dict for validation
        schemas_by_name = {}
        if tool_schemas:
            for schema in tool_schemas:
                name = schema.get("name")
                if name:
                    schemas_by_name[name] = schema
        
        validation_errors = None
        for attempt in range(max_retries + 1):
            prompt = self._build_prompt(
                user_query, 
                available_tools,
                tool_schemas=tool_schemas,
                validation_errors=validation_errors,
                project_context=project_context,
            )
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
            
            plan = self._normalize_plan(data)
            
            # Validate plan if schemas provided
            if schemas_by_name:
                validation_errors = self.validate_plan(plan, schemas_by_name)
                if not validation_errors:
                    # Plan is valid, return it
                    return plan
                
                # If we have validation errors and retries left, try again
                if attempt < max_retries:
                    continue
            
            # Return plan (either no schemas provided or final attempt)
            return plan
        
        return []
