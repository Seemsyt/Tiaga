from graph import workflow
from langchain_core.messages import HumanMessage
import asyncio

async def chat(prompt:str):
    input_ = {'messages':[HumanMessage(content=prompt)]}

    async for event in workflow.astream_events(
    input=input_,
    version="v2"
):
          if event["event"] == "on_tool_start":
            print(f"\n🔧 Calling tool: {event['name']}")

        #   elif event["event"] == "on_tool_end":
        #     print(f"\n✅ Tool result: {event['data']}")

          elif event["event"] == "on_chat_model_stream":
            if "chunk" in event["data"]:
                chunk = event["data"]["chunk"]
                if chunk.content:
                    print(chunk.content, end="", flush=True)
            

while True:
    prompt = input("\n You ")
    if prompt.lower().strip() in ['exit','bye','quit','see you']:
        break
    asyncio.run(chat(prompt))