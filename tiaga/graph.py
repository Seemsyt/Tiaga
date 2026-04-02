import json
import re
import time
from datetime import datetime
from os import getenv
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from langchain_community.tools import DuckDuckGoSearchResults
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import tools_condition, ToolNode
from langgraph.graph import END, START, StateGraph, add_messages

from .youtube_scrapping import get_youtube_transcript
from .files_handling.file import (
    read_file, replace_in_file, write_file, create_folder,
    append_to_file, list_files, file_tree, move_item, get_cwd,
    delete_item
)

load_dotenv()

# ── Models ────────────────────────────────────────────────────────────────────

_model_kwargs = dict(
    model="stepfun/step-3.5-flash:free",
    api_key=getenv("OPEN_ROUTER_API_KEY"),
    base_url=getenv("BASE_URL", "https://openrouter.ai/api/v1"),
    streaming=True,
    temperature=0.7,
)

model = ChatOpenAI(**_model_kwargs)
coding_model = ChatOpenAI(**{**_model_kwargs, "temperature": 0.2})  # lower temp for code
summary_model = ChatOpenAI(**{**_model_kwargs, "temperature": 0.1})

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
    Use for: drafting code, debugging ideas, explanations, refactoring plans,
    or other programming help. This tool only returns text. If the user wants
    files created or changed, follow up with the file tools yourself.

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
    summary: str
    last_summary_index: int


SYSTEM_PROMPT = SystemMessage(content="""
You are Tiaga, an AI CLI assistant with access to tools for file operations and web search.

Your job is to solve tasks efficiently by deciding whether to:

1. Answer directly
2. Use a tool
3. Combine both

---

CORE BEHAVIOR:

* Be direct, precise, and action-oriented.
* No filler, no unnecessary explanations.
* Prioritize solving over explaining.

---

TOOL USAGE RULES:

You have access to:

* File tools (read, write, edit, list files)
* Web search tool

Use tools ONLY when needed.

---

WHEN TO USE FILE TOOLS:

* When the task involves user files, code, or directories
* When asked to modify, debug, or analyze code
* When context is missing and exists in files

Examples:

* "fix this project"
* "read main.py"
* "update config"
* "find bug in repo"

---

WHEN TO USE WEB SEARCH:

* When information is external or up-to-date
* When unsure about facts, APIs, versions, or libraries

Examples:

* "latest version of fastapi"
* "how bitnet works"
* "recent news"

---

WHEN NOT TO USE TOOLS:

* If the answer is already known and simple
* If user provided full context

---

DECISION MAKING:

* Prefer file tools over guessing
* Prefer web search over hallucination
* If unsure → ask a short clarification

---

OUTPUT FORMAT:

If using tools:

* Think step-by-step internally
* Return only final result (not tool reasoning)

If not using tools:

* Respond directly

---

CODING RULES:

* Return complete, working code
* No placeholders
* Minimal explanation unless asked

---

ERROR HANDLING:

* If user is wrong → correct them directly
* If task is ambiguous → ask one clear question
* Do not proceed with assumptions

---

CLI OPTIMIZATION:

* Output must be copy-paste friendly
* Prefer commands and scripts
* Avoid long paragraphs

---

GOAL:
Act like a smart terminal assistant that uses tools only when necessary and never guesses when it can verify.

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
    file_tree, move_item, get_cwd, delete_item,
]

agent     = model.bind_tools(tools)
tool_node = ToolNode(tools)


def retry_with_backoff(max_retries: int = 3, initial_delay: float = 1.0, backoff_factor: float = 2.0):
    """Retry helper for flaky model calls."""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except Exception:
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(delay)
                    delay *= backoff_factor
        return wrapper
    return decorator


def _format_for_summary(message: BaseMessage) -> str:
    if isinstance(message, HumanMessage):
        role = "user"
    elif isinstance(message, AIMessage):
        role = "assistant"
    else:
        role = getattr(message, "type", message.__class__.__name__)
    content = message.content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or item))
            else:
                parts.append(str(item))
        text = " ".join(parts)
    else:
        text = str(content)
    return f"{role}: {text}"


def _is_visible_conversation_message(message: BaseMessage) -> bool:
    """Only summarize real user/assistant conversation, not tool plumbing."""
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


def chat_node(state: ChatState):
    @retry_with_backoff(max_retries=3, initial_delay=2, backoff_factor=1.5)
    def invoke_agent():
        messages = state.get("messages", [])
        if not messages:
            raise ValueError("No messages provided")

        system_prompt = SystemMessage(content=SYSTEM_PROMPT.content)
        summary = state.get("summary", "")
        if summary:
            system_prompt.content += f"\n\nSummary of past conversation:\n{summary}"

        recent_msgs = messages[-30:]
        return agent.invoke([system_prompt] + recent_msgs)

    response = invoke_agent()
    return {"messages": [response]}


def cleanup(state: ChatState):
    messages = state.get("messages", [])
    summary = state.get("summary", "")
    last_idx = state.get("last_summary_index", 0)

    chunk_size = 30
    max_msgs = 120
    keep_recent = 15

    new_messages = len(messages) - last_idx

    if new_messages >= chunk_size:
        to_summarize = [
            message
            for message in messages[last_idx : last_idx + chunk_size]
            if _is_visible_conversation_message(message)
        ]
        if not to_summarize:
            return {"last_summary_index": last_idx + chunk_size}
        formatted = "\n".join(_format_for_summary(m) for m in to_summarize)

        if summary:
            prompt = (
                "Existing summary:\n"
                f"{summary}\n\n"
                "Extend the summary with the following conversation chunk:\n"
                f"{formatted}"
            )
        else:
            prompt = f"Summarize this conversation chunk:\n{formatted}"

        new_summary = summary_model.invoke(prompt).content
        return {
            "summary": new_summary,
            "last_summary_index": last_idx + chunk_size,
        }

    if len(messages) > max_msgs and last_idx > keep_recent:
        delete_upto = max(0, last_idx - keep_recent)
        safe_to_delete = [
            message
            for message in messages[:delete_upto]
            if not isinstance(message, HumanMessage) or getattr(message, "id", None)
        ]
        if safe_to_delete:
            return {"messages": [RemoveMessage(id=m.id) for m in safe_to_delete if getattr(m, "id", None)]}

    return {}


def route_after_chat(state: ChatState):
    route = tools_condition(state)
    if route == "tools":
        return "tools"
    return "cleanup"


graph = StateGraph(ChatState)
graph.add_node("chat_node", chat_node)
graph.add_node("tools", tool_node)
graph.add_node("cleanup", cleanup)
graph.add_edge(START, "chat_node")
graph.add_conditional_edges("chat_node", route_after_chat)
graph.add_edge("tools", "chat_node")
graph.add_edge("cleanup", END)

# Compiled without checkpointer — main.py wires it in at runtime
workflow = graph.compile()
