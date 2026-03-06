import httpx
import logging
import json
import asyncio
import os
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import JSONResponse
from typing import Dict, Any, List
from datetime import datetime

from .manager import ModelManager, AGENT_TOOLS, LocalTools
from .models import OllamaProvisionRequest
from .config import load_config

# Initialize configuration and manager
config_path = os.environ.get("RANGECRAWLER_CONFIG", "config.yaml")
config = load_config(config_path)
manager = ModelManager(config)

logger = logging.getLogger("BrokerServer")
logging.basicConfig(
    level=getattr(logging, config.logging_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

app = FastAPI(title="RangeCrawler Reverse Proxy Agent")

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """Whitelist IP check for all requests except registration, clients, workers, and commands."""
    open_paths = [
        "/register", "/register/ssh", "/clients", 
        "/worker/register", "/worker/models", "/health", "/command/submit", 
        "/command/pending", "/command/result", "/command/status", "/chat/context"
    ]
    if any(request.url.path.startswith(p) for p in open_paths):
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

@app.post("/register/ssh")
async def register_ssh(request: Request):
    """Dynamically register SSH workspace for the calling client."""
    from .models import AgentWorkspaceConfig
    body = await request.json()
    client_ip = request.client.host if request.client else None
    if not client_ip:
        raise HTTPException(status_code=400, detail="Unable to determine client IP")
    
    try:
        ssh_cfg = AgentWorkspaceConfig(
            client_ip=client_ip,
            ssh_host=body["ssh_host"],
            ssh_port=body.get("ssh_port", 22),
            ssh_username=body["ssh_username"],
            ssh_pkey_path=body.get("ssh_pkey_path"),
            ssh_host_key=body.get("ssh_host_key"),
            working_directory=body.get("working_directory", ".")
        )
        manager.register_ip(client_ip, ssh_config=ssh_cfg)
        
        # Return the latest worker public key to the client for automatic authorization
        conn = manager.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT public_key FROM worker_keys ORDER BY last_seen DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        
        worker_key = row[0] if row else None
        
        return {
            "status": "ok", 
            "ip": client_ip, 
            "workspace": "ssh",
            "worker_public_key": worker_key
        }
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing required field: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/worker/register")
async def register_worker(request: Request):
    """Register a worker's public key."""
    body = await request.json()
    public_key = body.get("public_key")
    if not public_key:
        raise HTTPException(status_code=400, detail="Missing public_key")
    
    conn = manager.get_db()
    cursor = conn.cursor()
    # Use a fixed ID of 1 to ensure we only ever have ONE active worker key
    cursor.execute("INSERT OR REPLACE INTO worker_keys (id, public_key, last_seen) VALUES (1, ?, CURRENT_TIMESTAMP)", (public_key,))
    conn.commit()
    conn.close()
    
    return {"status": "ok", "message": "Worker public key registered"}

@app.post("/worker/models")
async def register_models(request: Request):
    """Register models available on a worker."""
    from .models import ModelConfig
    body = await request.json()
    models_data = body.get("models", [])
    
    models = [ModelConfig(**m) for m in models_data]
    manager.register_models(models)
    
    return {"status": "ok", "registered_count": len(models)}

# --- CHAT CONTEXT CACHE ---
# In-memory store for the latest context.json of each client.
# This avoids constant SSH 'cat' commands from the CLI.
context_cache: Dict[str, Any] = {}

@app.post("/chat/context/{client_ip}")
async def update_chat_context(client_ip: str, request: Request):
    """Worker pushes the latest context for a client here."""
    body = await request.json()
    context_cache[client_ip] = body
    return {"status": "ok"}

@app.get("/chat/context/{client_ip}")
async def get_chat_context(client_ip: str):
    """Client CLI polls this to see if the AI has finished."""
    context = context_cache.get(client_ip)
    if not context:
        return JSONResponse(status_code=404, content={"detail": "No context found for this client."})
    return context

@app.post("/command/submit")
async def submit_command(request: Request):
    """Submit a command to be executed on a specific client."""
    body = await request.json()
    client_ip = body.get("client_ip")
    command = body.get("command")
    
    if not client_ip or not command:
        raise HTTPException(status_code=400, detail="Missing client_ip or command")
    
    conn = manager.get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO command_queue (client_ip, command) VALUES (?, ?)", (client_ip, command))
    command_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {"status": "ok", "command_id": command_id}

@app.get("/command/pending/{client_ip}")
async def get_pending_commands(client_ip: str):
    """Fetch pending commands for a specific client."""
    conn = manager.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, command FROM command_queue WHERE client_ip = ? AND status = 'pending'", (client_ip,))
    rows = cursor.fetchall()
    conn.close()
    
    return {"commands": [{"id": r[0], "command": r[1]} for r in rows]}

@app.post("/command/result")
async def post_command_result(request: Request):
    """Submit the result of an executed command."""
    body = await request.json()
    command_id = body.get("command_id")
    result = body.get("result")
    
    conn = manager.get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE command_queue SET status = 'completed', result = ? WHERE id = ?", (result, command_id))
    conn.commit()
    conn.close()
    
    return {"status": "ok"}

@app.get("/command/status/{command_id}")
async def get_command_status(command_id: int):
    """Get the status and result of a specific command."""
    conn = manager.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT status, result, command FROM command_queue WHERE id = ?", (command_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Command not found")
    
    return {
        "id": command_id,
        "status": row[0],
        "result": row[1],
        "command": row[2]
    }

async def forward_to_llm_api(model_id: str, path: str, body: Dict[str, Any]):
    """Low-level forwarder for a single turn with the remote API."""
    target_base = await manager.get_endpoint(model_id)
    target_url = target_base.rstrip("/") + "/" + path.lstrip("/")
    
    logger.debug(f"Forwarding chat request for model {model_id} to {target_url}")
    
    async with httpx.AsyncClient(timeout=config.broker.request_timeout) as client:
        resp = await client.post(target_url, json=body)
        if resp.status_code != 200:
            logger.error(f"Upstream API Error ({resp.status_code}): {resp.text}")
            try:
                err_data = resp.json()
            except Exception:
                err_data = {"error": resp.text}
            raise HTTPException(status_code=resp.status_code, detail=err_data)
        return resp.json()

async def execute_single_tool(func_name: str, func_args_str: str, workspace_context: Any, client_ip: str):
    """Wrapper to execute one tool and catch errors."""
    from typing import Callable
    from .models import AgentWorkspaceConfig
    from .manager import RemoteTools

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
            if is_remote:
                return workspace_context.working_directory
            return str(workspace_context.name)
        elif func_name in tool_map:
            return await tool_map[func_name](workspace_context, **args)
        else:
            return f"Error: Tool '{func_name}' is not supported."
    except Exception as e:
        return f"Error during tool execution: {str(e)}"

async def agent_loop(model_id: str, messages: List[Dict[str, Any]], client_ip: str):
    """Recursive agent loop with PARALLEL tool execution."""
    
    current_messages = list(messages)
    max_iterations = config.agent.max_iterations
    workspace_context = manager.get_workspace_context(client_ip)
    
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
                logger.info(f"[*] AGENT TOOL CALL [{client_ip}]: {func_name}({func_args})")
                
                tasks.append(execute_single_tool(func_name, func_args, workspace_context, client_ip))
            
            # Execute all tools concurrently
            results = await asyncio.gather(*tasks)
            
            # Append results in order
            for i, result in enumerate(results):
                tool_call = tool_calls[i]
                func_name = tool_call["function"]["name"]
                logger.info(f"[+] TOOL RESULT [{client_ip}]: {func_name} -> {str(result)[:200]}...")
                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": func_name,
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

@app.get("/clients")
async def list_clients():
    """Returns a list of all registered clients for the worker to poll."""
    conn = manager.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT ip, ssh_host, ssh_port, ssh_username, ssh_pkey_path, working_directory, ssh_host_key FROM allowed_ips WHERE ssh_host IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()
    
    clients = []
    for row in rows:
        clients.append({
            "ip": row[0],
            "ssh_host": row[1],
            "ssh_port": row[2],
            "ssh_username": row[3],
            "ssh_pkey_path": row[4],
            "working_directory": row[5],
            "ssh_host_key": row[6]
        })
    return {"clients": clients}

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
        "data": [{"id": mid, "object": "model", "owned_by": "rangecrawler"} for mid in manager.allowed_models.keys()]
    }

@app.post("/v1/request-ollama")
async def request_ollama_provisioning(request: Request, body: OllamaProvisionRequest):
    """
    Client VM requests a localized Ollama API tunnel.
    The Broker assigns this to a worker and enqueues a provisioning command.
    """
    client_ip = request.client.host if request.client else None
    if not client_ip or not manager.is_allowed(client_ip):
        raise HTTPException(status_code=403, detail="Client IP not authorized.")
    
    # 1. Select the 'best' worker. For now, we take the first worker that reported models.
    # In a real cyber range, this would involve VRAM/load balancing.
    worker_models = list(manager.allowed_models.values())
    if not worker_models:
        raise HTTPException(status_code=503, detail="No workers currently available.")
    
    # Identify target client config (SSH details)
    client_cfg = manager.get_workspace_context(client_ip)
    from .models import AgentWorkspaceConfig
    if not isinstance(client_cfg, AgentWorkspaceConfig):
        raise HTTPException(status_code=400, detail="Client machine must be registered via SSH agent to use tunnels.")

    # 2. Build the command payload
    provision_cmd = {
        "action": "provision_isolated_ollama",
        "model": body.model,
        "timeout": body.timeout_minutes,
        "client_ip": client_ip,
        "target_port": 11434 # The port on the CLIENT machine
    }
    
    # 3. Queue the command for the worker to pick up
    conn = manager.get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO command_queue (client_ip, command) VALUES (?, ?)",
        (client_ip, json.dumps(provision_cmd))
    )
    conn.commit()
    conn.close()
    
    logger.info(f"[PROVISION] Queued Ollama {body.model} for {client_ip}")
    return {
        "status": "accepted",
        "message": f"Inference provision for {body.model} is starting. Access will be via localhost:11434 on your VM shortly.",
        "model": body.model
    }
