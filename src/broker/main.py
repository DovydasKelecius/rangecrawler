import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import load_config
from .db.database import DatabaseManager
from .services.tunnel import TunnelManager
from .routers import admin, chat, commands, system

# Global instances for dependency injection
config_path = os.environ.get("RANGECRAWLER_CONFIG", "config.yaml")
config = load_config(config_path)
db_manager = DatabaseManager(config)
tunnel_manager = TunnelManager()

logging.basicConfig(
    level=getattr(logging, config.logging_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

app = FastAPI(title="RangeCrawler Broker")

# Dependency injection helpers
def get_config(): return config
def get_db(): return db_manager
def get_tunnels(): return tunnel_manager

app.dependency_overrides[load_config] = get_config
app.dependency_overrides[DatabaseManager] = get_db
app.dependency_overrides[TunnelManager] = get_tunnels

from fastapi.responses import JSONResponse, FileResponse

@app.get("/install")
async def get_install_script():
    script_path = os.path.join(os.path.dirname(__file__), "../../scripts/install.sh")
    return FileResponse(script_path, media_type="text/x-shellscript")

@app.get("/uninstall")
async def get_uninstall_script():
    script_path = os.path.join(os.path.dirname(__file__), "../../scripts/uninstall.sh")
    return FileResponse(script_path, media_type="text/x-shellscript")

@app.get("/download/agent")
async def download_agent():
    agent_path = os.path.join(os.path.dirname(__file__), "../agent/headless_client.py")
    return FileResponse(agent_path, media_type="text/x-python")

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    open_paths = [
        "/register", "/register/ssh", "/agents", 
        "/worker/register", "/worker/models", "/health", "/command/", "/chat/context",
        "/admin", "/v1/models", "/install", "/download", "/handshake/"
    ]
    if any(request.url.path.startswith(p) for p in open_paths):
        return await call_next(request)

    # For chat/completion routes, check X-Client-UUID
    client_uuid = request.headers.get("X-Client-UUID")
    if client_uuid:
        # Permission check happens in the router for specific models
        return await call_next(request)

    # For internal agent routes, check X-Agent-UUID
    agent_uuid = request.headers.get("X-Agent-UUID")
    if agent_uuid and db_manager.is_agent_registered(agent_uuid):
        return await call_next(request)

    return JSONResponse(status_code=403, content={"detail": "Unauthorized. Client or Agent UUID required."})

# Include routers
app.include_router(system.router)
app.include_router(admin.router)
app.include_router(chat.router)
app.include_router(commands.router)

@app.on_event("shutdown")
def shutdown_event():
    tunnel_manager.cleanup()
