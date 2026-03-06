import uvicorn
import httpx
import argparse
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

app = FastAPI(title="RangeCrawler Ollama Shield Proxy")

# Whitelist endpoints allowed for isolated client access
ALLOWED_PATHS = {
    "/api/generate", "/api/chat", "/api/embeddings", 
    "/api/tags", "/api/version", "/api/show"
}

OLLAMA_BASE_URL = "http://localhost:11434"

@app.middleware("http")
async def isolation_filter(request: Request, call_next):
    """Ensure ONLY whitelisted paths can be accessed."""
    path = request.url.path
    if path not in ALLOWED_PATHS:
        return Response(content="[SECURITY BLOCK] This endpoint is restricted in the cyber range.", status_code=403)
    return await call_next(request)

@app.api_route("/{path:path}", methods=["GET", "POST", "HEAD", "OPTIONS"])
async def proxy_inference(request: Request, path: str):
    """Forward inference requests with streaming support."""
    client = httpx.AsyncClient(base_url=OLLAMA_BASE_URL)
    url = httpx.URL(path=f"/{path}", query=request.url.query.encode("utf-8"))
    
    # Track the last time a request was made (for inactivity timeouts)
    # Note: In a real multi-process env, this would update a shared file/socket.
    
    async def stream_generator():
        async with client.stream(
            request.method, url,
            content=await request.body(),
            headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
            timeout=None
        ) as resp:
            async for chunk in resp.aiter_raw():
                yield chunk
        await client.aclose()

    return StreamingResponse(stream_generator())

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=11435)
    args = parser.parse_args()
    
    uvicorn.run(app, host="127.0.0.1", port=args.port)
