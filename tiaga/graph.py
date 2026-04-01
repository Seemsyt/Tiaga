from langgraph.graph import END, START, StateGraph, add_messages
from typing import TypedDict, Annotated
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from os import getenv
from datetime import datetime
from langgraph.prebuilt import tools_condition, ToolNode
from langchain_core.messages import HumanMessage, BaseMessage, AIMessage, SystemMessage
from langchain_community.tools import DuckDuckGoSearchResults
from langchain_core.tools import tool
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from youtube_scrapping import get_youtube_transcript
from files_handling.file import (
    read_file, replace_in_file, write_file, create_folder,
    append_to_file, list_files, file_tree, move_item, get_cwd
)
import json
import re

load_dotenv()

# ── Models ────────────────────────────────────────────────────────────────────

_model_kwargs = dict(
    model="stepfun/step-3.5-flash:free",
    api_key=getenv("OPEN_ROUTER_API_KEY"),
    base_url=getenv("BASE_URL"),
    streaming=True,
    temperature=0.7,
)

model = ChatOpenAI(**_model_kwargs)
coding_model = ChatOpenAI(**{**_model_kwargs, "temperature": 0.2})  # lower temp for code

# ── Raw search backend (no tool wrapper yet) ──────────────────────────────────

_ddg_search = DuckDuckGoSearchResults(max_results=8, output_format="list")

# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def get_current_datetime() -> str:
    """Return the current date and time. Call this before any time-sensitive search."""
    now = datetime.now()
    return json.dumps({
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "year": now.year,
        "month": now.strftime("%B %Y"),
    })


@tool
def web_search(query: str) -> str:
    """
    Search the web for up-to-date information.

    Tips for best results:
    - Include the current year for time-sensitive topics (e.g. "Python 3.13 release notes 2025")
    - Use specific, targeted queries rather than vague ones
    - For news/events, append "latest" or the current year to the query
    - Call get_current_datetime first if you need to know today's date

    Args:
        query: A specific, well-formed search query.

    Returns:
        Formatted search results with title, URL, and snippet for each result.
    """
    try:
        raw_results = _ddg_search.invoke(query)
    except Exception as e:
        # Retry once with a simplified query on failure
        try:
            simplified = re.sub(r'[^\w\s]', '', query)[:120]
            raw_results = _ddg_search.invoke(simplified)
        except Exception:
            return f"Search failed: {e}. Try rephrasing your query."

    if not raw_results:
        return "No results found. Try a different or broader query."

    # raw_results is a list of dicts when output_format="list"
    lines = [f"[Search: '{query}' — {datetime.now().strftime('%Y-%m-%d')}]\n"]
    seen_urls = set()

    for i, r in enumerate(raw_results, 1):
        url = r.get("link", r.get("url", ""))
        if url in seen_urls:          # de-duplicate
            continue
        seen_urls.add(url)

        title   = r.get("title", "No title").strip()
        snippet = r.get("snippet", r.get("body", "")).strip()
        snippet = re.sub(r'\s+', ' ', snippet)[:300]  # normalise whitespace

        lines.append(f"{i}. **{title}**")
        lines.append(f"   URL: {url}")
        lines.append(f"   {snippet}\n")

    return "\n".join(lines)


@tool
def multi_search(queries: list[str]) -> str:
    """
    Run multiple search queries in sequence and merge the results.
    Use this when a question requires information from several angles
    (e.g. comparing options, verifying facts from multiple sources).

    Args:
        queries: A list of 2–4 distinct, specific search queries.

    Returns:
        Combined search results from all queries, de-duplicated by URL.
    """
    if not queries or len(queries) > 4:
        return "Provide between 1 and 4 queries."

    seen_urls: set[str] = set()
    all_lines: list[str] = []

    for query in queries:
        try:
            raw = _ddg_search.invoke(query)
        except Exception as e:
            all_lines.append(f"[Query '{query}' failed: {e}]")
            continue

        all_lines.append(f"\n## Results for: '{query}'\n")
        count = 0
        for r in raw:
            url = r.get("link", r.get("url", ""))
            if url in seen_urls:
                continue
            seen_urls.add(url)
            title   = r.get("title", "No title").strip()
            snippet = re.sub(r'\s+', ' ', r.get("snippet", r.get("body", "")).strip())[:280]
            all_lines.append(f"- **{title}** ({url})\n  {snippet}")
            count += 1
            if count >= 5:
                break

    return "\n".join(all_lines) if all_lines else "No results found."


@tool
async def coding_agent(query: str) -> str:
    """
    Delegate a coding or programming task to a specialised coding model.
    Use for: writing code, debugging, explaining code, refactoring, or
    any task that is primarily about programming.

    Args:
        query: A clear description of the coding task or question.
    """
    coding_system = (
        "You are an expert software engineer. Provide concise, correct, "
        "well-commented code. Prefer idiomatic solutions. "
        "Always explain your approach briefly before the code block."
    )
    messages = [
        {"role": "system", "content": coding_system},
        {"role": "user",   "content": query},
    ]
    result = await coding_model.ainvoke(messages)
    return result.content


# ── State & prompt ────────────────────────────────────────────────────────────

class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


SYSTEM_PROMPT = SystemMessage(content="""
You are a highly capable AI assistant with access to web search and file tools.

## Search strategy
1. **Always call `get_current_datetime` first** when the query involves recent events,
   current prices, software versions, news, or anything time-sensitive.
2. Use `web_search` with a *specific* query that includes the current year when relevant.
3. For complex questions that need multiple perspectives, use `multi_search` with 2–3
   distinct queries instead of one broad search.
4. Synthesise results in your own words — do not just paste raw snippets.
5. If the first search returns poor results, refine the query and try once more.

## General rules
- Answer from your knowledge when no live data is needed.
- Use `coding_agent` for all programming tasks.
- Use file tools when the user references files or directories.
- Be concise but complete. Cite sources (URLs) when drawing on search results.
""")


# ── Graph ─────────────────────────────────────────────────────────────────────

tools = [
    get_current_datetime,
    web_search,
    multi_search,
    coding_agent,
    get_youtube_transcript,
    read_file, replace_in_file, write_file,
    create_folder, append_to_file, list_files,
    file_tree, move_item, get_cwd,
]

agent     = model.bind_tools(tools)
tool_node = ToolNode(tools)


def chat_node(state: ChatState):
    response = agent.invoke([SYSTEM_PROMPT] + state["messages"])
    return {"messages": [response]}


graph = StateGraph(ChatState)
graph.add_node("chat_node", chat_node)
graph.add_node("tools",     tool_node)
graph.add_edge(START, "chat_node")
graph.add_conditional_edges("chat_node", tools_condition)
graph.add_edge("tools", "chat_node")

# Compiled without checkpointer — main.py wires it in at runtime
workflow = graph.compile()