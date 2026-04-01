from langgraph.graph import END, START, StateGraph, add_messages
from typing import TypedDict, Annotated
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from os import getenv
from langgraph.prebuilt import tools_condition, ToolNode
from langchain_core.messages import HumanMessage, BaseMessage, AIMessage, SystemMessage
from langchain_community.tools import DuckDuckGoSearchResults,tool
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from files_handling.file import read_file,replace_in_file,write_file,create_folder,append_to_file,list_files,file_tree,move_item,get_cwd
load_dotenv()

search_tool = DuckDuckGoSearchResults()

model = ChatOpenAI(
    model='stepfun/step-3.5-flash',
    api_key=getenv("OPEN_ROUTER_API_KEY"),
    base_url=getenv("BASE_URL"),
    streaming=True,
    temperature=0.7
)
coding_model = ChatOpenAI(
    model='stepfun/step-3.5-flash',
    api_key=getenv("OPEN_ROUTER_API_KEY"),
    base_url=getenv("BASE_URL"),
    streaming=True,
    temperature=0.7
)

@tool
async def coding_agent(query: str) -> str:
    """Performs coding and programming tasks"""
    result = await coding_model.ainvoke(query)
    return result.content

class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

SYSTEM_PROMPT = SystemMessage(
    content="""
You are a helpful AI assistant.

Rules:
- Use the search tool for latest information.
- Answer normally if no tool is required.
"""
)

tools = [search_tool, coding_agent,read_file,replace_in_file,write_file,create_folder,append_to_file,list_files,file_tree,move_item,get_cwd]
agent = model.bind_tools(tools)
tool_node = ToolNode(tools)

def chat_node(state: ChatState):
    response = agent.invoke([SYSTEM_PROMPT] + state["messages"])
    return {"messages": [response]}

graph = StateGraph(ChatState)
graph.add_node("chat_node", chat_node)
graph.add_node("tools", tool_node)
graph.add_edge(START, "chat_node")
graph.add_conditional_edges("chat_node", tools_condition)
graph.add_edge("tools", "chat_node")

# Compiled without checkpointer — main.py wires it in at runtime
workflow = graph.compile()