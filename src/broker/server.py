from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
import httpx
import asyncio
import logging
from typing import Any, Dict

from .manager import ModelManager
from .config import load_config

# Load configuration
config = load_config()

# Configure logging
logging.basicConfig(
    level=config.logging_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("BrokerServer")

app = FastAPI(title="RangeCrawler Broker")
manager = ModelManager(config)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(manager.cleanup_idle())

@app.get("/v1/models")
async def list_models():
    # Return both loaded and allowed models
    models_data = []
    
    # 1. Add allowed (but not necessarily loaded) models
    for model_id in manager.allowed_models:
        # Check if loaded
        instances = manager.instances.get(model_id, [])
        models_data.append({
            "id": model_id,
            "object": "model",
            "created": int(instances[0].start_time.timestamp()) if instances else int(time.time()),
            "owned_by": "rangecrawler",
            "status": "loaded" if any(i.status == "running" for i in instances) else "available",
            "instances": len(instances),
            "active_requests": sum(inst.active_requests for inst in instances)
        })
    
    return {"object": "list", "data": models_data}

async def forward_request(model_id: str, path: str, body: Dict[str, Any]):
    instance = await manager.get_instance(model_id)
    target_url = f"http://localhost:{instance.port}{path}"
    
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            if body.get("stream"):
                return await _handle_streaming(client, target_url, body, instance)
            else:
                response = await client.post(target_url, json=body)
                return JSONResponse(content=response.json(), status_code=response.status_code)
    except Exception as e:
        logger.error(f"Error forwarding request: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await manager.release_instance(instance)

async def _handle_streaming(client: httpx.AsyncClient, url: str, body: dict, instance):
    # This is a bit complex as we need to ensure release_instance is called
    # after the stream finishes.
    req = client.build_request("POST", url, json=body)
    resp = await client.send(req, stream=True)
    
    async def iterate_stream():
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            await resp.aclose()
            await manager.release_instance(instance)
            
    return StreamingResponse(iterate_stream(), status_code=resp.status_code, media_type=resp.headers.get("content-type"))

@app.post("/v1/completions")
async def completions(request: Request):
    body = await request.json()
    model_id = body.get("model")
    if not model_id:
        raise HTTPException(status_code=400, detail="Missing model parameter")
    return await forward_request(model_id, "/v1/completions", body)

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    model_id = body.get("model")
    if not model_id:
        raise HTTPException(status_code=400, detail="Missing model parameter")
    return await forward_request(model_id, "/v1/chat/completions", body)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
