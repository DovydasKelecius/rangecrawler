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

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    open_paths = [
        "/register", "/register/ssh", "/clients", 
        "/worker/register", "/worker/models", "/health", "/command/", "/chat/context",
        "/admin", "/v1/models"
    ]
    if any(request.url.path.startswith(p) for p in open_paths):
        return await call_next(request)

    client_ip = request.client.host if request.client else None
    if not client_ip or not db_manager.is_allowed(client_ip):
        return JSONResponse(status_code=403, content={"detail": f"IP {client_ip} not registered."})

    return await call_next(request)

# Include routers
app.include_router(system.router)
app.include_router(admin.router)
app.include_router(chat.router)
app.include_router(commands.router)

@app.on_event("shutdown")
def shutdown_event():
    tunnel_manager.cleanup()
