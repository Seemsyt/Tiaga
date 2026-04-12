
from ddgs import DDGS

from pydantic import BaseModel
from pydantic import Field

from tiaga.context.text import truncate_text
from tiaga.tools_manager.base import Tool, Tool_kind, ToolInvocation, ToolResult



class WebSearchParams(BaseModel):
    query: str = Field(..., description="description search query")
    max_result: int = Field(
        10, ge=1,le=20,description="How many result you want to get from web search in numbers(intiger). (default is 10)"
    )
    


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web for information and return results with titles, URLs, and snippets."
    tool_kind = Tool_kind.NETWORK
    schema = WebSearchParams

    async def execute(self, invocation: ToolInvocation):
        params = WebSearchParams(**invocation.params)

        try:
            results = list(DDGS().text(params.query, region='us-en', safesearch='off', timelimit='y', page=1, backend="auto"))
        except Exception as e :
            return ToolResult.error_result(f"Search error: {e}")

        if not results:
            return ToolResult.success_result(f"no result found for query {params.query}")
        
        output_lines = [f"search result for:  {params.query}"]

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
            




        
        


        
        