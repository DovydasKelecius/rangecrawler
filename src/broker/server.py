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

    client_ip = request.client.host if request.client else "0.0.0.0"
    if not manager.is_allowed(client_ip):
        logger.warning(f"Unauthorized access attempt from {client_ip}")
        return JSONResponse(status_code=403, content={"detail": f"IP {client_ip} not registered."})

    response = await call_next(request)
    return response

@app.post("/register")
async def register_ip(request: Request):
    """Manually register the calling client IP for access."""
    client_ip = request.client.host if request.client else "0.0.0.0"
    registered = manager.register_ip(client_ip)
    return {"status": "ok", "ip": client_ip, "new_registration": registered}

async def forward_to_vllm(model_id: str, path: str, body: Dict[str, Any], client_ip: str):
    """Transparently proxy the request to the target vLLM endpoint."""
    target_base = await manager.get_endpoint(model_id)
    
    # OpenAI SDK path: /v1/chat/completions
    # Google OpenAI Base: https://.../v1beta/openai/
    # Google expects: https://.../v1beta/openai/chat/completions
    
    clean_path = path
    if "googleapis.com" in target_base and path.startswith("/v1/"):
        clean_path = path[3:] # Remove '/v1' -> '/chat/completions'

    target_url = target_base.rstrip("/") + "/" + clean_path.lstrip("/")
    
    headers = {}
    # Google AI Studio OpenAI-compatible endpoint accepts the key as a Bearer token
    if config.auth.gemini_api_key:
        headers["Authorization"] = f"Bearer {config.auth.gemini_api_key}"
    
    logger.info(f"Forwarding to: {target_url} (model: {model_id})")
    
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            if body.get("stream"):
                return await _handle_streaming(client, target_url, body, headers, client_ip)
            else:
                resp = await client.post(target_url, json=body, headers=headers)
                manager.track_usage(client_ip, 10) 
                
                try:
                    data = resp.json()
                    return JSONResponse(content=data, status_code=resp.status_code)
                except:
                    logger.error(f"Non-JSON response from {target_url}: {resp.text}")
                    return JSONResponse(content={"error": resp.text}, status_code=resp.status_code)
                    
    except Exception as e:
        logger.error(f"Proxy error for model {model_id} at {target_url}: {e}")
        raise HTTPException(status_code=502, detail=f"Target vLLM unavailable: {str(e)}")

async def _handle_streaming(client: httpx.AsyncClient, url: str, body: dict, headers: dict, client_ip: str):
    """Proxy streaming responses chunk-by-chunk."""
    req = client.build_request("POST", url, json=body, headers=headers)
    resp = await client.send(req, stream=True)
    
    async def iterate_stream():
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            await resp.aclose()
            manager.track_usage(client_ip, 50)
            
    return StreamingResponse(iterate_stream(), status_code=resp.status_code, media_type=resp.headers.get("content-type"))

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    model_id = body.get("model")
    if not model_id:
        raise HTTPException(status_code=400, detail="Missing model parameter")
    return await forward_to_vllm(model_id, "/v1/chat/completions", body, request.client.host if request.client else "0.0.0.0")

@app.post("/v1/completions")
async def completions(request: Request):
    body = await request.json()
    model_id = body.get("model")
    if not model_id:
        raise HTTPException(status_code=400, detail="Missing model parameter")
    return await forward_to_vllm(model_id, "/v1/completions", body, request.client.host if request.client else "0.0.0.0")

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
