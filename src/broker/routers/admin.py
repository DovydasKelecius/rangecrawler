from fastapi import APIRouter, Depends
from ..models import ModelConfig, ClientPermission
from ..db.database import DatabaseManager

router = APIRouter(prefix="/admin", tags=["admin"])

@router.post("/models")
async def add_model(model: ModelConfig, db: DatabaseManager = Depends()):
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO models_registry (id, remote_url, ssh_host, ssh_username, ssh_pkey_path, description, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            remote_url=excluded.remote_url,
            ssh_host=excluded.ssh_host,
            ssh_username=excluded.ssh_username,
            ssh_pkey_path=excluded.ssh_pkey_path,
            description=excluded.description,
            is_active=excluded.is_active
    ''', (model.id, model.remote_url, model.ssh_host, model.ssh_username, model.ssh_pkey_path, model.description, int(model.is_active)))
    conn.commit()
    conn.close()
    return {"status": "ok", "model_id": model.id}

@router.get("/models")
async def list_models(db: DatabaseManager = Depends()):
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, remote_url, is_active FROM models_registry")
    rows = cursor.fetchall()
    conn.close()
    return {"models": [{"id": r[0], "remote_url": r[1], "is_active": bool(r[2])} for r in rows]}

@router.post("/permissions/grant")
async def grant_permission(perm: ClientPermission, db: DatabaseManager = Depends()):
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO client_permissions (
            client_ip, model_id, allow_tools, max_usage_seconds, expires_at, 
            window_start, window_end, lease_duration, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(client_ip, model_id) DO UPDATE SET
            allow_tools=excluded.allow_tools,
            max_usage_seconds=excluded.max_usage_seconds,
            expires_at=excluded.expires_at,
            window_start=excluded.window_start,
            window_end=excluded.window_end,
            lease_duration=excluded.lease_duration,
            is_active=excluded.is_active
    ''', (
        perm.client_ip, perm.model_id, int(perm.allow_tools), perm.max_usage_seconds,
        perm.expires_at.isoformat() if perm.expires_at else None,
        perm.window_start, perm.window_end, perm.lease_duration, int(perm.is_active)
    ))
    conn.commit()
    conn.close()
    return {"status": "ok", "client_ip": perm.client_ip, "model_id": perm.model_id}

@router.get("/permissions")
async def list_permissions(db: DatabaseManager = Depends()):
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT client_ip, model_id, allow_tools, used_seconds, max_usage_seconds FROM client_permissions")
    rows = cursor.fetchall()
    conn.close()
    return {"permissions": [
        {"client_ip": r[0], "model_id": r[1], "allow_tools": bool(r[2]), "used_seconds": r[3], "max_usage_seconds": r[4]} 
        for r in rows
    ]}
