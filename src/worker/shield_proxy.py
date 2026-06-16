import uvicorn
import httpx
import argparse
import logging
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ShieldProxy")

app = FastAPI(title="RangeCrawler Ollama Shield Proxy")

# Whitelist prefixes allowed for isolated client access
ALLOWED_PREFIXES = {
    "/api/generate", "/api/chat", "/api/embeddings", 
    "/api/tags", "/api/version", "/api/show"
}

# Will be set via command line
OLLAMA_BASE_URL = "http://localhost:11434"

@app.middleware("http")
async def isolation_filter(request: Request, call_next):
    """Ensure ONLY whitelisted paths can be accessed."""
    path = request.url.path
    if not any(path.startswith(prefix) for prefix in ALLOWED_PREFIXES):
        logger.warning(f"BLOCKED: Attempted access to {path}")
        return Response(content="[SECURITY BLOCK] This endpoint is restricted in the cyber range.", status_code=403)
    return await call_next(request)

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def proxy_inference(request: Request, path: str):
    """Forward inference requests with status code transparency."""
    # Use a single client session for efficiency
    async with httpx.AsyncClient(base_url=OLLAMA_BASE_URL, timeout=600.0) as client:
        url = httpx.URL(path=f"/{path}", query=request.url.query.encode("utf-8"))
        body = await request.body()
        
        req = client.build_request(
            request.method, url,
            content=body,
            headers={k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
        )
        
        try:
            resp = await client.send(req, stream=True)
            
            from starlette.background import BackgroundTask
            return StreamingResponse(
                resp.aiter_raw(),
                status_code=resp.status_code,
                headers={k: v for k, v in resp.headers.items() if k.lower() not in ("content-encoding", "transfer-encoding", "content-length")},
                background=BackgroundTask(resp.aclose)
            )
        except Exception as e:
            logger.error(f"Proxy Error: {e}")
            return Response(content=f"Proxy Error: {str(e)}", status_code=502)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=11435)
    parser.add_argument("--ollama-url", type=str, default="http://localhost:11434")
    args = parser.parse_args()
    
    OLLAMA_BASE_URL = args.ollama_url
    logger.info(f"Shield Proxy active on port {args.port}, shielding {OLLAMA_BASE_URL}")
    uvicorn.run(app, host="127.0.0.1", port=args.port)
