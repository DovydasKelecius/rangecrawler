import httpx
import logging
import json
import asyncio
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import JSONResponse
from typing import Dict, Any, List
from datetime import datetime
from pathlib import Path

from .manager import ModelManager, AGENT_TOOLS, LocalTools
from .config import load_config

# Initialize configuration and manager
config = load_config()
manager = ModelManager(config)

logger = logging.getLogger("BrokerServer")
logging.basicConfig(
    level=getattr(logging, config.logging_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

app = FastAPI(title="RangeCrawler Reverse Proxy Agent")

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """Whitelist IP check for all requests except /register or /health."""
    if request.url.path in ["/register", "/health"]:
        return await call_next(request)

    client_ip = request.client.host if request.client else None
    if not client_ip or not manager.is_allowed(client_ip):
        logger.warning(f"Unauthorized access attempt from {client_ip}")
        return JSONResponse(status_code=403, content={"detail": f"IP {client_ip} not registered."})

    response = await call_next(request)
    return response

@app.get("/health")
async def health_check():
    """Returns the current status of the broker and its backend connectivity."""
    return {
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "database": "connected",
        "agent_mode": config.agent.enabled
    }

@app.post("/register")
async def register_ip(request: Request):
    """Manually register the calling client IP for access."""
    client_ip = request.client.host if request.client else None
    if not client_ip:
        raise HTTPException(status_code=400, detail="Unable to determine client IP")
    registered = manager.register_ip(client_ip)
    return {"status": "ok", "ip": client_ip, "new_registration": registered}

async def forward_to_llm_api(model_id: str, path: str, body: Dict[str, Any]):
    """Low-level forwarder for a single turn with the remote API."""
    target_base = await manager.get_endpoint(model_id)
    clean_path = path
    if "googleapis.com" in target_base and path.startswith("/v1"):
        clean_path = path[3:] # Remove '/v1'
    
    target_url = target_base.rstrip("/") + "/" + clean_path.lstrip("/")
    headers = {}
    if config.auth.gemini_api_key:
        headers["Authorization"] = f"Bearer {config.auth.gemini_api_key}"

    async with httpx.AsyncClient(timeout=config.broker.request_timeout) as client:
        resp = await client.post(target_url, json=body, headers=headers)
        if resp.status_code != 200:
            logger.error(f"Upstream API Error ({resp.status_code}): {resp.text}")
            try:
                err_data = resp.json()
            except Exception:
                err_data = {"error": resp.text}
            raise HTTPException(status_code=resp.status_code, detail=err_data)
        return resp.json()

async def execute_single_tool(func_name: str, func_args_str: str, workspace_path: Path, client_ip: str):
    """Wrapper to execute one tool and catch errors."""
    from typing import Callable, Awaitable
    tool_map: Dict[str, Callable[..., Awaitable[Any]]] = {
        "read_file": LocalTools.read_file,
        "write_file": LocalTools.write_file,
        "list_directory": LocalTools.list_directory,
        "run_bash": LocalTools.run_bash
    }
    
    try:
        args = json.loads(func_args_str)
        if func_name == "get_current_directory":
            return str(workspace_path.name)
        elif func_name in tool_map:
            return await tool_map[func_name](workspace_path, **args)
        else:
            return f"Error: Tool '{func_name}' is not supported."
    except Exception as e:
        return f"Error during tool execution: {str(e)}"

async def agent_loop(model_id: str, messages: List[Dict[str, Any]], client_ip: str):
    """Recursive agent loop with PARALLEL tool execution."""
    
    current_messages = list(messages)
    max_iterations = config.agent.max_iterations
    workspace_path = manager.get_workspace_path(client_ip)
    
    for iteration in range(max_iterations):
        logger.info(f"Agent Loop iteration {iteration + 1}/{max_iterations}")
        
        body = {
            "model": model_id,
            "messages": current_messages,
            "tools": AGENT_TOOLS,
            "tool_choice": "auto"
        }
        
        response_data = await forward_to_llm_api(model_id, "/v1/chat/completions", body)
        manager.track_usage(client_ip, 100)
        
        choice = response_data["choices"][0]
        message = choice["message"]
        
        if "tool_calls" in message and message["tool_calls"]:
            current_messages.append(message)
            
            # --- PARALLEL EXECUTION LOGIC ---
            tool_calls = message["tool_calls"]
            tasks = []
            
            for tool_call in tool_calls:
                func_name = tool_call["function"]["name"]
                func_args = tool_call["function"]["arguments"]
                logger.info(f"Agent ({client_ip}) queueing parallel tool: {func_name}")
                
                tasks.append(execute_single_tool(func_name, func_args, workspace_path, client_ip))
            
            # Execute all tools concurrently
            results = await asyncio.gather(*tasks)
            
            # Append results in order
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
            response_data["system_fingerprint"] = "fp_rangecrawler_agent_v1"
            return response_data

    raise HTTPException(status_code=504, detail="Agent loop limit reached.")

@app.post("/v1/chat/completions")
async def chat_completions(request: Request, response: Response):
    body = await request.json()
    model_id = body.get("model")
    messages = body.get("messages", [])
    client_ip = request.client.host if request.client else None
    if not client_ip:
        raise HTTPException(status_code=400, detail="Unable to determine client IP")
    
    if not model_id:
        raise HTTPException(status_code=400, detail="Missing model parameter")
    
    final_response = await agent_loop(model_id, messages, client_ip)
    response.headers["X-RangeCrawler-Agent"] = "true"
    
    return final_response

@app.get("/stats")
async def get_stats():
    """Returns usage statistics for all registered sessions."""
    return {
        "total_sessions": len(manager.sessions),
        "sessions": [
            {
                "ip": s.ip,
                "token_usage": s.token_usage,
                "last_active": s.last_active.isoformat(),
                "uptime_seconds": (datetime.now() - s.start_time).total_seconds()
            }
            for s in manager.sessions.values()
        ]
    }

@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [{"id": mid, "object": "model", "owned_by": "rangecrawler"} for mid in manager.allowed_models]
    }
