import asyncio
import fnmatch
import os
import re
from pathlib import Path


import signal
import sys

from pydantic import BaseModel,Field
from tiaga.tools_manager.base import Tool, Tool_kind, ToolConfirmation, ToolInvocation, ToolResult


BLOCKED_PATTERNS = [
    # File destruction
    r'\brm\s+-r[fF]?\b',
    r'\bunlink\b',
    r'\bshred\b',
    r'\bwipe\b',
    
    # Disk / filesystem damage
    r'\bdd\b',
    r'\bmkfs\b',
    r'\bfsck\b',
    r'\bfdisk\b',
    r'\bparted\b',
    r'\bmount\b',
    r'\bumount\b',
    
    # Permission abuse
    r'\bchmod\s+777\b',
    r'\bchmod\s+-R\s+777\b',
    r'\bchown\b',
    
    # System control
    r'\bshutdown\b',
    r'\breboot\b',
    r'\bhalt\b',
    r'\bpoweroff\b',
    r'\binit\s+[06]\b',
    
    # Fork bomb
    r':\s*\(\s*\)\s*\{',
    
    # Privilege escalation
    r'\bsudo\b',
    r'\bsu\b',
    
    # Network abuse / remote execution
    r'\bcurl\b',
    r'\bwget\b',
    r'\bnc\b',
    r'\bnetcat\b',
    r'\bssh\b',
    
    # Process killing
    r'\bkill\s+-9\b',
    r'\bpkill\b',
    r'\bkillall\b',
    
    # Dangerous writes
    r'>\s*/dev/sda',
    r'>\s*/dev/null',
    
    # Environment damage
    r'\bexport\s+PATH=',
]


class ShellParams(BaseModel):
    command:str = Field(...,description="The shell command to execute")
    timeout:int = Field(120,ge=1,le=600,description="Timeout in second(default is 120)")
    cwd:str|None = Field(None,description="working directory for the command")

class ShellTool(Tool):
    name = "shell"
    tool_kind = Tool_kind.SHELL
    description = "Execute a shell command. Use this for running system commands, scripts and CLI tools."
    MAX_DISPLAY_OUTPUT_BYTES = 100 * 1024

    schema = ShellParams

    def _build_environment(self)->dict[str,str]:
        env = os.environ.copy()

        shell_environment =  self.config.shell_environment

        if not shell_environment.ignore_default_excludes:
            for pattern in shell_environment.excludes_patterns:
                keys_to_remove = [key for key in env.keys() if fnmatch.fnmatch(key.upper(),pattern.upper())]
                
                for k in keys_to_remove :
                    del env[k]

        if shell_environment.set_vars:
            env.update(shell_environment.set_vars)

        return env

    async def get_confirmation(self, invocation:ToolInvocation)->ToolConfirmation|None:
        params = ShellParams(**invocation.params)

        for pattern in BLOCKED_PATTERNS:
            if re.search(pattern, params.command, re.IGNORECASE):
                return ToolConfirmation(
                    tool_name=self.name,
                    params=invocation.params,
                    description=f"Execute (Blocked) command {params.command}",
                    command=params.command,
                    is_dangerous=True,
                )
        return ToolConfirmation(
            tool_name=self.name,
            params=invocation.params,
            description=f"Execute {params.command}",
            command=params.command,
            is_dangerous= False

        )

    async def execute(self, invocation:ToolInvocation)->ToolResult:
        params = ShellParams(**invocation.params)


        command = params.command.strip()
        for pattern in BLOCKED_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return ToolResult.error_result(
                    f"Command blocked for safety: {params.command}",
                    metadata={
                        "blocked":True
                    }
                )
        if params.cwd:
            cwd = Path(params.cwd)
            if not cwd.is_absolute():
                cwd = invocation.cwd/cwd
        else:
            cwd = invocation.cwd
        if not cwd.exists() :
            return ToolResult.error_result(f"Working directory does not exits: {cwd}")
        
        env = self._build_environment()

        if sys.platform == "win32":
            shell_cmd = ['cmd.exe','/c',params.command]
        else :
            shell_cmd = ['/bin/bash',"-c",params.command]

        process = await asyncio.create_subprocess_exec(*shell_cmd,
                                                       stdout=asyncio.subprocess.PIPE,
                                                       stderr=asyncio.subprocess.PIPE,
                                                       cwd=cwd,
                                                       env=env,
                                                       start_new_session=True)
        try:
            stdout_data,stderr_data = await asyncio.wait_for(process.communicate(),timeout=params.timeout)
        except asyncio.TimeoutError as e :
            if sys.platform != "win32":
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass  # Process already terminated
            else :
                process.kill()
            await process.wait()
            return ToolResult.error_result(f"Command timed out after {params.timeout}s")
        
        except asyncio.CancelledError:       
            if sys.platform != "win32":
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:
                process.kill()
                await process.wait()
                raise      
        stdout = stdout_data.decode("utf-8",errors="replace")
        stderr = stderr_data.decode("utf-8",errors="replace")
        exit_code  = process.returncode
        output = ""
        if stdout.strip():
            output += stdout.rstrip()

        if stderr.strip():
            output += "\n-----stderror-----\n"
            output += stderr.rstrip()

        if exit_code != 0:
            output +=f"\nexit code  {exit_code}"

        display_output = None
        is_truncated = False
        if len(output) > self.MAX_DISPLAY_OUTPUT_BYTES:
            display_output = (
                output[: self.MAX_DISPLAY_OUTPUT_BYTES] + "\n... [output truncated for display]"
            )
            is_truncated = True

        return ToolResult(success=exit_code == 0,
            output=output,
            error=stderr if exit_code != 0 else None,
            display_output=display_output,
            truncated=is_truncated,
            exit_code=exit_code,
        )


        
