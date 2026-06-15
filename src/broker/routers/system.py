import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from datetime import datetime
from ..config import load_config
from ..db.database import DatabaseManager
from ..models import AppConfig, AgentWorkspaceConfig

router = APIRouter(tags=["system"])
logger = logging.getLogger(__name__)

@router.get("/health")
async def health_check(config: AppConfig = Depends(load_config)):
    return {
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "database": "connected",
        "agent_mode": config.agent.enabled
    }

@router.post("/register")
async def register_agent(request: Request, db: DatabaseManager = Depends()):
    body = await request.json()
    agent_uuid = body.get("agent_uuid")
    if not agent_uuid:
        raise HTTPException(status_code=400, detail="Missing agent_uuid")
    registered = db.register_agent(agent_uuid)
    return {"status": "ok", "agent_uuid": agent_uuid, "new_registration": registered}

@router.post("/register/ssh")
async def register_ssh(request: Request, db: DatabaseManager = Depends()):
    body = await request.json()
    agent_uuid = body.get("agent_uuid")
    if not agent_uuid:
        raise HTTPException(status_code=400, detail="Missing agent_uuid")
    
    try:
        ssh_cfg = AgentWorkspaceConfig(
            agent_uuid=agent_uuid,
            ssh_host=body["ssh_host"],
            ssh_port=body.get("ssh_port", 22),
            ssh_username=body["ssh_username"],
            ssh_pkey_path=body.get("ssh_pkey_path"),
            ssh_host_key=body.get("ssh_host_key")
        )
        db.register_agent(agent_uuid, ssh_config=ssh_cfg)
        
        conn = db.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT public_key FROM worker_keys ORDER BY last_seen DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        
        return {
            "status": "ok", 
            "agent_uuid": agent_uuid, 
            "workspace": "ssh",
            "worker_public_key": row[0] if row else None
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/handshake/init")
async def init_handshake(request: Request, db: DatabaseManager = Depends()):
    body = await request.json()
    agent_uuid = body.get("agent_uuid")
    public_key = body.get("public_key")
    scope = body.get("scope", "shell")
    if not agent_uuid or not public_key:
        raise HTTPException(status_code=400, detail="Missing agent_uuid or public_key")
    
    # Generate challenge
    import secrets
    challenge = secrets.token_hex(32)
    
    conn = db.get_db()
    cursor = conn.cursor()
    # Store pending handshake
    cursor.execute('''
        INSERT OR REPLACE INTO pending_handshakes (agent_uuid, public_key, challenge, scope, status)
        VALUES (?, ?, ?, ?, 'pending')
    ''', (agent_uuid, public_key, challenge, scope))
    conn.commit()
    conn.close()
    
    return {"status": "ok", "challenge": challenge}

@router.get("/handshake/poll/{agent_uuid}")
async def poll_handshake(agent_uuid: str, db: DatabaseManager = Depends()):
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT public_key, challenge, scope FROM pending_handshakes WHERE agent_uuid = ? AND status = 'pending'", (agent_uuid,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {"status": "none"}
    return {"status": "pending", "public_key": row[0], "challenge": row[1], "scope": row[2]}

@router.post("/handshake/confirm")
async def confirm_handshake(request: Request, db: DatabaseManager = Depends()):
    body = await request.json()
    agent_uuid = body.get("agent_uuid")
    if not agent_uuid:
        raise HTTPException(status_code=400, detail="Missing agent_uuid")
    
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE pending_handshakes SET status = 'confirmed' WHERE agent_uuid = ?", (agent_uuid,))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@router.get("/handshake/verify/{agent_uuid}")
async def verify_handshake(agent_uuid: str, db: DatabaseManager = Depends()):
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM pending_handshakes WHERE agent_uuid = ?", (agent_uuid,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0] == "confirmed":
        return {"status": "confirmed"}
    return {"status": "pending"}

@router.post("/worker/register")
async def register_worker(request: Request, db: DatabaseManager = Depends()):
    return {"status": "ok"}

@router.post("/worker/models")
async def register_models(request: Request, db: DatabaseManager = Depends()):
    body = await request.json()
    models_data = body.get("models", [])
    
    conn = db.get_db()
    cursor = conn.cursor()
    for m in models_data:
        cursor.execute('''
            INSERT INTO models_registry (id, remote_url, is_active)
            VALUES (?, ?, 1)
            ON CONFLICT(id) DO UPDATE SET remote_url=excluded.remote_url, is_active=1
        ''', (m["id"], m["remote_url"]))
    conn.commit()
    conn.close()
    return {"status": "ok", "registered_count": len(models_data)}

@router.get("/agents")
async def list_agents(db: DatabaseManager = Depends()):
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT uuid, ssh_host, ssh_port, ssh_username, ssh_pkey_path, ssh_host_key FROM registered_agents WHERE ssh_host IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()
    return {"agents": [
        {"uuid": r[0], "ssh_host": r[1], "ssh_port": r[2], "ssh_username": r[3], "ssh_pkey_path": r[4], "ssh_host_key": r[5]}
        for r in rows
    ]}
