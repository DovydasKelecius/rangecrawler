import logging
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from datetime import datetime
from typing import Dict, Any
from ..config import load_config
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
    client_uuid = request.headers.get("X-Client-UUID")
    if not client_uuid:
        return {"object": "list", "data": []}
    permitted = db.get_permitted_models(client_uuid)
    return {"object": "list", "data": [{"id": m.id, "object": "model"} for m in permitted]}

@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request, 
    response: Response, 
    db: DatabaseManager = Depends(), 
    config: AppConfig = Depends(load_config),
    tunnels: TunnelManager = Depends()
):
    body = await request.json()
    model_id = body.get("model")
    messages = body.get("messages", [])
    client_uuid = request.headers.get("X-Client-UUID") or body.get("client_uuid")
    agent_uuid = request.headers.get("X-Agent-UUID") or body.get("agent_uuid")

    if not client_uuid or not model_id:
        raise HTTPException(status_code=400, detail="Missing client UUID or model parameter")

    permission = db.check_access(client_uuid, model_id)
    if not permission:
        raise HTTPException(status_code=403, detail=f"Permission denied for model {model_id}")

    # Determine workspace context
    workspace = None
    if agent_uuid:
        workspace = db.get_agent_config(agent_uuid)
    
    if not workspace:
        # If no agent provided, we still need some context for the loop but it's optional now
        workspace = {}

    try:
        async def get_ep(mid):
            models = db.get_models()
            if mid not in models:
                raise HTTPException(status_code=503, detail="Model not available")
            return await tunnels.get_endpoint(mid, models[mid])

        final_response = await agent_loop(
            model_id=model_id,
            messages=messages,
            client_uuid=client_uuid,
            workspace_context=workspace,
            get_endpoint_fn=get_ep,
            check_access_fn=db.check_access,
            config=config
        )
        response.headers["X-RangeCrawler-Agent"] = "true"
        return final_response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chat/context/{agent_uuid}")
async def update_chat_context(agent_uuid: str, request: Request):
    body = await request.json()
    context_cache[agent_uuid] = body
    return {"status": "ok"}

@router.get("/chat/context/{agent_uuid}")
async def get_chat_context(agent_uuid: str):
    context = context_cache.get(agent_uuid)
    if not context:
        raise HTTPException(status_code=404, detail="No context found")
    return context

@router.post("/v1/request-ollama")
async def provision_ollama(request: Request, body: OllamaProvisionRequest, db: DatabaseManager = Depends()):
    client_uuid = request.headers.get("X-Client-UUID")
    agent_uuid = request.headers.get("X-Agent-UUID")
    
    if not client_uuid or not agent_uuid:
        raise HTTPException(status_code=400, detail="Missing client or agent UUID")
    
    permission = db.check_access(client_uuid, body.model)
    if not permission:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    agent_cfg = db.get_agent_config(agent_uuid)
    if not agent_cfg:
        raise HTTPException(status_code=400, detail="Agent not registered with SSH")

    provision_cmd = {
        "action": "provision_isolated_ollama",
        "model": body.model,
        "timeout": body.timeout_minutes,
        "agent_uuid": agent_uuid,
        "target_port": 11434
    }
    
    import json
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO command_queue (agent_uuid, command) VALUES (?, ?)", (agent_uuid, json.dumps(provision_cmd)))
    conn.commit()
    conn.close()
    
    return {"status": "accepted", "message": "Provisioning started."}
