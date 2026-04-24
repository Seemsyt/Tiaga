#!/usr/bin/env python3
import os
import sys
import json
from datetime import datetime
import uuid
from tiaga.config.loader import get_data_dir

def main():
    trigger = os.environ.get("AI_AGENT_TRIGGER")
    cwd = os.environ.get("AI_AGENT_CWD")
    tool_name = os.environ.get("AI_AGENT_TOOL_NAME")
    user_message = os.environ.get("AI_AGENT_USER_MESSAGE")
    error = os.environ.get("AI_AGENT_ERROR")

    log_data = {
        "timestamp": datetime.now().isoformat(),
        "trigger": trigger,
        "cwd": cwd,
        "tool_name": tool_name,
        "user_message": user_message,
        "error": error,
    }
    hook_id = uuid.uuid4()
    
    log_path = get_data_dir()/"logs"/"traces.log"
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a") as f:
        f.write(f"[HOOK] hook_id:{hook_id}, {json.dumps(log_data)}\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
