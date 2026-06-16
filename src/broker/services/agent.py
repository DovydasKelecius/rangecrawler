import json
import asyncio
import logging
import httpx
from typing import List, Dict, Any, Callable
from fastapi import HTTPException
from ..models import AppConfig

logger = logging.getLogger(__name__)

async def forward_to_llm_api(target_url: str, body: Dict[str, Any], timeout: float):
    """Low-level forwarder for a single turn with the remote API."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(target_url, json=body)
        if resp.status_code != 200:
            logger.error(f"Upstream API Error ({resp.status_code}): {resp.text}")
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()

async def agent_loop(
    model_id: str, 
    messages: List[Dict[str, Any]], 
    client_uuid: str, 
    workspace_context: Any,
    get_endpoint_fn: Callable,
    check_access_fn: Callable,
    config: AppConfig
):
    current_messages = list(messages)
    
    # Re-verify access
    if not check_access_fn(client_uuid, model_id):
        raise HTTPException(status_code=403, detail="Access denied.")

    target_url = await get_endpoint_fn(model_id)
    chat_url = target_url.rstrip("/") + "/v1/chat/completions"

    body = {"model": model_id, "messages": current_messages}
    
    response_data = await forward_to_llm_api(chat_url, body, config.broker.request_timeout)
    return response_data
