import uvicorn
import httpx
import argparse
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

app = FastAPI(title="RangeCrawler Ollama Shield Proxy")

# Whitelist prefixes allowed for isolated client access
ALLOWED_PREFIXES = {
    "/api/generate", "/api/chat", "/api/embeddings", 
    "/api/tags", "/api/version", "/api/show"
}

OLLAMA_BASE_URL = "http://localhost:11434"

@app.middleware("http")
async def isolation_filter(request: Request, call_next):
    """Ensure ONLY whitelisted paths can be accessed."""
    path = request.url.path
    if not any(path.startswith(prefix) for prefix in ALLOWED_PREFIXES):
        return Response(content="[SECURITY BLOCK] This endpoint is restricted in the cyber range.", status_code=403)
    return await call_next(request)

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def proxy_inference(request: Request, path: str):
    """Forward inference requests with status code transparency."""
    # Create client with no timeout for long-running inference
    client = httpx.AsyncClient(base_url=OLLAMA_BASE_URL, timeout=None)
    
    url = httpx.URL(path=f"/{path}", query=request.url.query.encode("utf-8"))
    body = await request.body()
    
    req = client.build_request(
        request.method, url,
        content=body,
        headers={k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    )
    
    resp = await client.send(req, stream=True)
    
    return StreamingResponse(
        resp.aiter_raw(),
        status_code=resp.status_code,
        headers={k: v for k, v in resp.headers.items() if k.lower() not in ("content-encoding", "transfer-encoding", "content-length")},
        background=resp.aclose
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=11435)
    args = parser.parse_args()
    
    uvicorn.run(app, host="127.0.0.1", port=args.port)
