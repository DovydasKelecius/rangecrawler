import json
import asyncio
import logging
import httpx
from typing import List, Dict, Any, Callable
from fastapi import HTTPException
from ..models import AppConfig, AgentWorkspaceConfig
from .tools import AGENT_TOOLS, LocalTools, RemoteTools

logger = logging.getLogger(__name__)

async def forward_to_llm_api(target_url: str, body: Dict[str, Any], timeout: float):
    """Low-level forwarder for a single turn with the remote API."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(target_url, json=body)
        if resp.status_code != 200:
            logger.error(f"Upstream API Error ({resp.status_code}): {resp.text}")
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()

async def execute_single_tool(func_name: str, func_args_str: str, workspace_context: Any, client_ip: str):
    is_remote = isinstance(workspace_context, AgentWorkspaceConfig)
    tool_impl = RemoteTools if is_remote else LocalTools
    
    tool_map: Dict[str, Callable] = {
        "read_file": tool_impl.read_file,
        "write_file": tool_impl.write_file,
        "list_directory": tool_impl.list_directory,
        "run_bash": tool_impl.run_bash
    }
    
    try:
        args = json.loads(func_args_str)
        if func_name == "get_current_directory":
            return workspace_context.working_directory if is_remote else str(workspace_context)
        elif func_name in tool_map:
            return await tool_map[func_name](workspace_context, **args)
        else:
            return f"Error: Tool '{func_name}' is not supported."
    except Exception as e:
        return f"Error during tool execution: {str(e)}"

async def agent_loop(
    model_id: str, 
    messages: List[Dict[str, Any]], 
    client_ip: str, 
    workspace_context: Any,
    get_endpoint_fn: Callable,
    check_access_fn: Callable,
    config: AppConfig,
    allow_tools: bool = True
):
    current_messages = list(messages)
    max_iterations = config.agent.max_iterations

    for iteration in range(max_iterations):
        logger.info(f"Agent Loop iteration {iteration + 1}/{max_iterations} for {client_ip}")

        # Re-verify access window between every iteration
        if not check_access_fn(client_ip, model_id):
            raise HTTPException(status_code=403, detail="Access expired or usage quota reached.")

        target_url = await get_endpoint_fn(model_id)
        chat_url = target_url.rstrip("/") + "/v1/chat/completions"

        body = {"model": model_id, "messages": current_messages}
        if allow_tools:
            body["tools"] = AGENT_TOOLS
            body["tool_choice"] = "auto"

        response_data = await forward_to_llm_api(chat_url, body, config.broker.request_timeout)

        choice = response_data["choices"][0]
        message = choice["message"]

        if allow_tools and "tool_calls" in message and message["tool_calls"]:
            current_messages.append(message)
            tool_calls = message["tool_calls"]
            tasks = [execute_single_tool(tc["function"]["name"], tc["function"]["arguments"], workspace_context, client_ip) for tc in tool_calls]
            results = await asyncio.gather(*tasks)

            for i, result in enumerate(results):
                tool_call = tool_calls[i]
                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": tool_call["function"]["name"],
                    "content": str(result)
                })
            continue
        else:
            return response_data

    raise HTTPException(status_code=504, detail="Agent loop limit reached.")
