from fastapi import FastAPI, Request
import uvicorn
import logging

app = FastAPI(title="Mock LLM Service")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MockLLM")

@app.get("/api/port")
async def get_port():
    """Mock dynamic port service."""
    logger.info("Broker requested dynamic port assignment.")
    return {"port": 8000}

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """Mock OpenAI-style chat completion endpoint."""
    body = await request.json()
    model = body.get("model", "unknown")
    logger.info(f"Received request for model: {model}")
    
    return {
        "id": "mock-chat-123",
        "object": "chat.completion",
        "created": 1700000000,
        "model": model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant", 
                "content": f"Success! This response for model '{model}' was proxied through RangeCrawler."
            },
            "finish_reason": "stop"
        }]
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
