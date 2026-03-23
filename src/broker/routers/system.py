import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from datetime import datetime
from ..db.database import DatabaseManager
from ..models import AppConfig, AgentWorkspaceConfig

router = APIRouter(tags=["system"])
logger = logging.getLogger(__name__)

@router.get("/health")
async def health_check(config: AppConfig = Depends()):
    return {
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "database": "connected",
        "agent_mode": config.agent.enabled
    }

@router.post("/register")
async def register_ip(request: Request, db: DatabaseManager = Depends()):
    client_ip = request.client.host if request.client else None
    if not client_ip:
        raise HTTPException(status_code=400, detail="Unable to determine client IP")
    registered = db.register_ip(client_ip)
    return {"status": "ok", "ip": client_ip, "new_registration": registered}

@router.post("/register/ssh")
async def register_ssh(request: Request, db: DatabaseManager = Depends()):
    body = await request.json()
    client_ip = request.client.host if request.client else None
    if not client_ip:
        raise HTTPException(status_code=400, detail="Unable to determine client IP")
    
    try:
        ssh_cfg = AgentWorkspaceConfig(
            client_ip=client_ip,
            ssh_host=body["ssh_host"],
            ssh_port=body.get("ssh_port", 22),
            ssh_username=body["ssh_username"],
            ssh_pkey_path=body.get("ssh_pkey_path"),
            ssh_host_key=body.get("ssh_host_key"),
            working_directory=body.get("working_directory", ".")
        )
        db.register_ip(client_ip, ssh_config=ssh_cfg)
        
        conn = db.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT public_key FROM worker_keys ORDER BY last_seen DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        
        return {
            "status": "ok", 
            "ip": client_ip, 
            "workspace": "ssh",
            "worker_public_key": row[0] if row else None
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/worker/register")
async def register_worker(request: Request, db: DatabaseManager = Depends()):
    body = await request.json()
    public_key = body.get("public_key")
    if not public_key:
        raise HTTPException(status_code=400, detail="Missing public_key")
    
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO worker_keys (id, public_key, last_seen) VALUES (1, ?, CURRENT_TIMESTAMP)", (public_key,))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@router.get("/clients")
async def list_clients(db: DatabaseManager = Depends()):
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT ip, ssh_host, ssh_port, ssh_username, ssh_pkey_path, working_directory, ssh_host_key FROM allowed_ips WHERE ssh_host IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()
    return {"clients": [
        {"ip": r[0], "ssh_host": r[1], "ssh_port": r[2], "ssh_username": r[3], "ssh_pkey_path": r[4], "working_directory": r[5], "ssh_host_key": r[6]}
        for r in rows
    ]}
