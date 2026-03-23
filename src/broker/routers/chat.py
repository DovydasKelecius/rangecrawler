import logging
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from datetime import datetime
from typing import Dict, Any, List
from ..db.database import DatabaseManager
from ..models import AppConfig, OllamaProvisionRequest
from ..services.agent import agent_loop
from ..services.tunnel import TunnelManager

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)

# Global state that will be injected
context_cache: Dict[str, Any] = {}

@router.get("/v1/models")
async def list_models(request: Request, db: DatabaseManager = Depends()):
    client_ip = request.client.host if request.client else None
    if not client_ip: return {"object": "list", "data": []}
    permitted = db.get_permitted_models(client_ip)
    return {"object": "list", "data": [{"id": m.id, "object": "model"} for m in permitted]}

@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request, 
    response: Response, 
    db: DatabaseManager = Depends(), 
    config: AppConfig = Depends(),
    tunnels: TunnelManager = Depends()
):
    body = await request.json()
    model_id = body.get("model")
    messages = body.get("messages", [])
    client_ip = request.client.host if request.client else None

    if not client_ip or not model_id:
        raise HTTPException(status_code=400, detail="Missing client IP or model parameter")

    permission = db.check_access(client_ip, model_id)
    if not permission:
        raise HTTPException(status_code=403, detail=f"Permission denied for model {model_id}")

    workspace = db.get_workspace_config(client_ip) or db.db_path # Fallback to a safe local path? 
    # Actually, in the old manager it defaulted to a local path.
    if not workspace:
        # Re-implementing logic from old manager.get_workspace_context
        from pathlib import Path
        safe_ip = client_ip.replace(":", "_").replace(".", "-")
        workspace = Path(config.agent.working_directory).resolve() / f"agent_{safe_ip}"
        workspace.mkdir(parents=True, exist_ok=True)

    start_time = datetime.now()
    try:
        async def get_ep(mid):
            models = db.get_models()
            if mid not in models: raise HTTPException(status_code=503, detail="Model not available")
            return await tunnels.get_endpoint(mid, models[mid])

        final_response = await agent_loop(
            model_id=model_id,
            messages=messages,
            client_ip=client_ip,
            workspace_context=workspace,
            get_endpoint_fn=get_ep,
            check_access_fn=db.check_access,
            config=config,
            allow_tools=permission.allow_tools
        )
        duration = int((datetime.now() - start_time).total_seconds())
        db.record_usage(client_ip, model_id, max(1, duration))
        response.headers["X-RangeCrawler-Agent"] = "true"
        return final_response
    except Exception as e:
        duration = int((datetime.now() - start_time).total_seconds())
        db.record_usage(client_ip, model_id, max(1, duration))
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chat/context/{client_ip}")
async def update_chat_context(client_ip: str, request: Request):
    body = await request.json()
    context_cache[client_ip] = body
    return {"status": "ok"}

@router.get("/chat/context/{client_ip}")
async def get_chat_context(client_ip: str):
    context = context_cache.get(client_ip)
    if not context: raise HTTPException(status_code=404, detail="No context found")
    return context

@router.post("/v1/request-ollama")
async def provision_ollama(request: Request, body: OllamaProvisionRequest, db: DatabaseManager = Depends()):
    client_ip = request.client.host if request.client else None
    if not client_ip: raise HTTPException(status_code=400, detail="Missing client IP")
    
    permission = db.check_access(client_ip, body.model)
    if not permission: raise HTTPException(status_code=403, detail="Permission denied")
    
    client_cfg = db.get_workspace_config(client_ip)
    if not client_cfg: raise HTTPException(status_code=400, detail="Client not registered with SSH")

    provision_cmd = {
        "action": "provision_isolated_ollama",
        "model": body.model,
        "timeout": body.timeout_minutes,
        "client_ip": client_ip,
        "target_port": 11434
    }
    
    import json
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO command_queue (client_ip, command) VALUES (?, ?)", (client_ip, json.dumps(provision_cmd)))
    conn.commit()
    conn.close()
    
    return {"status": "accepted", "message": "Provisioning started."}
