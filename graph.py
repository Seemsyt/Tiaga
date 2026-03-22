from langgraph.graph import END, START, StateGraph,add_messages
from typing import TypedDict,Annotated
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from os import getenv
from langgraph.prebuilt import tools_condition,ToolNode
from langchain_core.messages import HumanMessage,BaseMessage,AIMessage, SystemMessage, ToolMessage
from langchain_tavily import TavilySearch
from langchain_core.tools import tool

load_dotenv()



search_tool = TavilySearch()




coding_model = ChatOpenAI(
    model='stepfun/step-3.5-flash:free',  # Try a different model that supports tools
    api_key=getenv("OPEN_ROUTER_API_KEY"),
    base_url=getenv("BASE_URL"),
    streaming=True,
    temperature=0.7
)
model = ChatOpenAI(
    model='arcee-ai/trinity-large-preview:free',  # Try a different model that supports tools
    api_key=getenv("OPEN_ROUTER_API_KEY"),
    base_url=getenv("BASE_URL"),
    streaming=True,
    temperature=0.7
)
# for chunk in model.stream([HumanMessage(content="Explain quantum physics")]):
#     print(chunk.content, end="", flush=True)


@tool
def coding_agent(query: str) -> str:
    """This is a model that performs task related to coding and programming"""
    result = coding_model.invoke(query)
    return result.content

class ChatState(TypedDict):
    messages:Annotated[list[BaseMessage],add_messages]


def chat_node(state: ChatState):

    messages = state["messages"]

    system_prompt = SystemMessage(
        content="""
You are a helpful AI assistant.

Rules:
- Use the search tool for latest information.

- Answer normally if no tool is required.
"""
    )

    response = agent.invoke([system_prompt] + messages)

    return {
        "messages": [response]
    }


tools = [search_tool, coding_agent]
agent = model.bind_tools(tools)


tool_node = ToolNode(tools)

graph = StateGraph(ChatState)
graph.add_node('chat_node',chat_node)
graph.add_node("tools", tool_node)

graph.add_edge(START,"chat_node")
graph.add_conditional_edges('chat_node',tools_condition)
graph.add_edge('tools','chat_node')
workflow = graph.compile()

print("workflow was called")