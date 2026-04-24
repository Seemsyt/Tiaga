
from ddgs import DDGS

import re
from datetime import datetime

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator

from tiaga.context.text import truncate_text
from tiaga.tools_manager.base import Tool, Tool_kind, ToolInvocation, ToolResult



class WebSearchParams(BaseModel):
    query: str = Field(..., description="description search query")
    max_result: int = Field(
        10, ge=1,le=20,description="How many result you want to get from web search in numbers(intiger). (default is 10)"
    )
    time_limit: str = Field(
        "y",
        description="How far back to search: 'd' (day), 'w' (week), 'm' (month), 'y' (year). Default 'y'.",
    )

    @field_validator("time_limit")
    @classmethod
    def validate_time_limit(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in {"d", "w", "m", "y"}:
            raise ValueError("time_limit must be one of: d, w, m, y")
        return v
    


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web for information and return results with titles, URLs, and snippets."
    tool_kind = Tool_kind.NETWORK
    schema = WebSearchParams

    async def execute(self, invocation: ToolInvocation):
        params = WebSearchParams(**invocation.params)
        original_query = params.query

        # Guardrail: if a query includes a past year but the caller is asking for
        # very recent results (day/week/month), drop the year token so we don't
        # accidentally anchor "latest" searches to an outdated year.
        current_year = datetime.now().year
        if params.time_limit in {"d", "w", "m"}:
            years = {int(y) for y in re.findall(r"\b(?:19|20)\d{2}\b", params.query)}
            past_years = {y for y in years if y != current_year}
            if past_years:
                params.query = re.sub(r"\b(?:19|20)\d{2}\b", "", params.query)
                params.query = re.sub(r"\s{2,}", " ", params.query).strip()

        try:
            results = list(
                DDGS().text(
                    params.query,
                    region="us-en",
                    safesearch="off",
                    timelimit=params.time_limit,
                    page=1,
                    backend="auto",
                )
            )
        except Exception as e :
            return ToolResult.error_result(f"Search error: {e}")

        if not results:
            return ToolResult.success_result(f"no result found for query {params.query}")
        
        output_lines = [f"search result for:  {params.query}"]
        if original_query != params.query:
            output_lines.insert(0, f"note: normalized query from: {original_query}")

        for i , result in enumerate(results,start=1):
            output_lines.append(f"{i}. Titles: {result['title']} ")
            output_lines.append(f" Url: {result['href']} ")
            snippet = result.get("body")
            if snippet:
                output_lines.append(f" Snippet: {snippet}")

            output_lines.append("")

        

        output = "\n".join(output_lines)

        display_output = None
        is_truncated = False

        maybe_truncated = truncate_text(
            output,
            model="gpt-4o-mini",
            max_tokens=240,
            suffix="\n...[truncated for display]",
        )

        if maybe_truncated != output:
            display_output = maybe_truncated
            is_truncated = True

        return ToolResult.success_result(
            output=output,
            display_output=display_output,
            truncated=is_truncated,
            metadata={
                "query": params.query,
                "lines": len(results),

            },
        )
            




        
        


        
        
