import asyncio
from dataclasses import  dataclass
from typing import Any

from pydantic import BaseModel,Field


from tiaga.config.config import Config
from tiaga.tools_manager.base import Tool, ToolInvocation, ToolResult



class SubAgentParams(BaseModel):
    goal:str = Field(...,description="The specific task or goal for the subagent to accomplish")


@dataclass
class SubAgentDefinition():
    name:str
    description:str
    goal_prompt:str
    allowed_tools:list[str]
    max_turns:int|None = 20
    timeout:float|None = 600.00 

class SubagentTool(Tool):
    def __init__(self, config: Config, definition: SubAgentDefinition):
        super().__init__(config)
        self.definition = definition

    @property
    def name(self) -> str:
        return f"subagent_{self.definition.name}"

    @property
    def description(self) -> str:
        return f"subagent_{self.definition.description}"
    schema = SubAgentParams

    def is_mutating(self,params:dict[str,Any]):
        return True
    
    async def execute(self, invocation:ToolInvocation)->ToolResult:
        from tiaga.agent.agent import Agent
        from tiaga.agent.events import AgentEvent, AgentEventType
        params = SubAgentParams(**invocation.params)
        if not params.goal:
            return ToolResult.error_result("No goal specified for sub-agent")
        config_dict = self.config.to_dict()
        config_dict["max_turns"] = self.definition.max_turns
        if self.definition.allowed_tools:
            config_dict['allowed_tools'] = self.definition.allowed_tools

        sub_agent = Config(**config_dict)

        prompt = f"""You are a specialized sub-agent with a specific task to complete.

        {self.definition.goal_prompt}

        YOUR TASK:
        {params.goal}

        IMPORTANT:
        - Focus only on completing the specified task
        - Do not engage in unrelated actions
        - Once you have completed the task or have the answer, provide your final response
        - Be concise and direct in your output
        """
        tool_call_list = []
        final_response = None
        error_output = None
        terminate_response = 'hit-goal'
        try:
            async with Agent(sub_agent) as agent:
                deadline = asyncio.get_event_loop().time() + self.definition.timeout

                async for event in agent.run(prompt):
                    if asyncio.get_event_loop().time()>deadline:
                        terminate_response = "timeout"
                        final_response = "Sub-agent timed-out"
                        break
                    if event.type == AgentEventType.TOOL_CALL_START:
                        tool_call_list.append(event.data.get("name"))

                    if event.type == AgentEventType.TOOL_CALL_END:
                        final_response = event.data.get("output","")
                    elif event.type== AgentEventType.AGENT_ERROR:
                        error_output = event.data.get("error","Unknown")
                        terminate_response="Error"
                        final_response = f"Sub-Agent error occured {error_output}"
                        break



        except Exception as e:
            terminate_response = "Error"
            error = str(e)
            final_response= f"Sub-agent failed{e}"


        result = f"""SubAgent '{self.definition.name}' completed.
          Termination reason {terminate_response}
        Tool called {','.join(tool_call_list) if tool_call_list else "None"}  
        Final response{final_response if final_response else "None"}"""

        if error:
            return ToolResult.error_result(f"{result}")
        
        return ToolResult.success_result(result)
    


CODEBASE_INVESTIGATOR = SubAgentDefinition(
    name="codebase_investigator",
    description="Investigates the codebase to answer questions about code structure, patterns, and implementations",
    goal_prompt="""You are a codebase investigation specialist.
Your job is to explore and understand code to answer questions.
Use read_file, grep, glob, and list_dir to investigate.
Do NOT modify any files.""",
    allowed_tools=["read_file", "grep", "glob", "list_dir"],
)

CODE_REVIEWER = SubAgentDefinition(
    name="code_reviewer",
    description="Reviews code changes and provides feedback on quality, bugs, and improvements",
    goal_prompt="""You are a code review specialist.
Your job is to review code and provide constructive feedback.
Look for bugs, code smells, security issues, and improvement opportunities.
Use read_file, list_dir and grep to examine the code.
Do NOT modify any files.""",
    allowed_tools=["read_file", "grep", "list_dir"],
    max_turns=10,
    timeout=300,
)


def get_default_subagent_definition()->list[SubAgentDefinition]:
    return [
     CODE_REVIEWER,
     CODEBASE_INVESTIGATOR,
        ]
    
    