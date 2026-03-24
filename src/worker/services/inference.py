import httpx
import logging
from typing import List, Dict, Any, Optional
from .ssh_manager import execute_remote_tool

logger = logging.getLogger("WorkerInference")

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the content of a file from local disk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File name or relative path within your workspace."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with specific content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File name or relative path within your workspace."},
                    "content": {"type": "string", "description": "Full text content to write."}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and directories in your current workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path (default: '.')."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Execute a shell command in your workspace and return its output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The command to run."},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)."}
                },
                "required": ["command"]
            }
        }
    }
]

def call_ollama(ollama_url: str, model: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None):
    payload = {"model": model, "messages": messages, "stream": False}
    if tools:
        payload["tools"] = tools
    try:
        resp = httpx.post(f"{ollama_url}/api/chat", json=payload, timeout=120.0)
        if resp.status_code == 200:
            return resp.json().get("message")
        logger.error(f"Ollama error: {resp.status_code}")
    except Exception as e:
        logger.error(f"Failed to reach Ollama: {e}")
    return None

def get_ollama_models(ollama_url: str) -> List[str]:
    try:
        resp = httpx.get(f"{ollama_url}/api/tags", timeout=5.0)
        if resp.status_code == 200:
            return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        pass  # nosec
    return []

def worker_agent_loop(ssh, remote_path, model, messages, ollama_url):
    current_messages = list(messages)
    max_iterations = 10
    for iteration in range(max_iterations):
        response_msg = call_ollama(ollama_url, model, current_messages, tools=AGENT_TOOLS)
        if not response_msg:
            return None
        current_messages.append(response_msg)
        if "tool_calls" in response_msg and response_msg["tool_calls"]:
            for tool_call in response_msg["tool_calls"]:
                func_name = tool_call["function"]["name"]
                func_args = tool_call["function"]["arguments"]
                result = execute_remote_tool(ssh, remote_path, func_name, func_args)
                current_messages.append({"role": "tool", "content": str(result)})
            continue
        return response_msg
    return {"role": "assistant", "content": "Error: Max iterations reached."}
