import httpx
import logging
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Dict, Any

from .manager import ModelManager
from .config import load_config

# Initialize configuration and manager
config = load_config()
manager = ModelManager(config)

logger = logging.getLogger("BrokerServer")
logging.basicConfig(
    level=getattr(logging, config.logging_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

app = FastAPI(title="RangeCrawler Reverse Proxy")

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """Whitelist IP check for all requests except /register."""
    if request.url.path == "/register":
        return await call_next(request)

    client_ip = request.client.host if request.client else None
    if not client_ip or not manager.is_allowed(client_ip):
        logger.warning(f"Unauthorized access attempt from {client_ip}")
        return JSONResponse(status_code=403, content={"detail": f"IP {client_ip} not registered."})

    response = await call_next(request)
    return response

@app.post("/register")
async def register_ip(request: Request):
    """Manually register the calling client IP for access."""
    client_ip = request.client.host if request.client else None
    if not client_ip:
        raise HTTPException(status_code=400, detail="Unable to determine client IP")
    registered = manager.register_ip(client_ip)
    return {"status": "ok", "ip": client_ip, "new_registration": registered}

async def forward_to_vllm(model_id: str, path: str, body: Dict[str, Any], client_ip: str):
    """Transparently proxy the request to the target vLLM endpoint."""
    target_base = await manager.get_endpoint(model_id)
    target_url = f"{target_base}{path}"
    
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            # Handle streaming vs non-streaming
            if body.get("stream"):
                return await _handle_streaming(client, target_url, body, client_ip)
            else:
                resp = await client.post(target_url, json=body)
                manager.track_usage(client_ip, 10) # Placeholder: 10 token cost for non-stream
                return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except Exception as e:
        logger.error(f"Proxy error for model {model_id} at {target_url}: {e}")
        raise HTTPException(status_code=502, detail=f"Target vLLM unavailable: {str(e)}")

async def _handle_streaming(client: httpx.AsyncClient, url: str, body: dict, client_ip: str):
    """Proxy streaming responses chunk-by-chunk."""
    req = client.build_request("POST", url, json=body)
    resp = await client.send(req, stream=True)
    
    async def iterate_stream():
        try:
            async for chunk in resp.aiter_bytes():
                # Hook for future: parse chunk and subtract from budget
                yield chunk
        finally:
            await resp.aclose()
            manager.track_usage(client_ip, 50) # Placeholder: 50 token cost for stream
            
    return StreamingResponse(iterate_stream(), status_code=resp.status_code, media_type=resp.headers.get("content-type"))

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    model_id = body.get("model")
    if not model_id:
        raise HTTPException(status_code=400, detail="Missing model parameter")
    client_ip = request.client.host if request.client else None
    if not client_ip:
        raise HTTPException(status_code=400, detail="Unable to determine client IP")
    return await forward_to_vllm(model_id, "/v1/chat/completions", body, client_ip)

@app.post("/v1/completions")
async def completions(request: Request):
    body = await request.json()
    model_id = body.get("model")
    if not model_id:
        raise HTTPException(status_code=400, detail="Missing model parameter")
    client_ip = request.client.host if request.client else None
    if not client_ip:
        raise HTTPException(status_code=400, detail="Unable to determine client IP")
    return await forward_to_vllm(model_id, "/v1/completions", body, client_ip)

@app.get("/v1/models")
async def list_models():
    """Returns the list of proxyable models."""
    return {
        "object": "list",
        "data": [
            {"id": mid, "object": "model", "owned_by": "rangecrawler"} 
            for mid in manager.allowed_models
        ]
    }
