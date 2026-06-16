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
            client_uuid, model_id, is_active
        ) VALUES (?, ?, ?)
        ON CONFLICT(client_uuid, model_id) DO UPDATE SET
            is_active=excluded.is_active
    ''', (
        perm.client_uuid, perm.model_id, int(perm.is_active)
    ))
    conn.commit()
    conn.close()
    return {"status": "ok", "client_uuid": perm.client_uuid, "model_id": perm.model_id}

@router.get("/permissions")
async def list_permissions(db: DatabaseManager = Depends()):
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT client_uuid, model_id, is_active FROM client_permissions")
    rows = cursor.fetchall()
    conn.close()
    return {"permissions": [
        {"client_uuid": r[0], "model_id": r[1], "is_active": bool(r[2])} 
        for r in rows
    ]}

@router.post("/agent/permit")
async def permit_agent(agent_uuid: str, permit: bool = True, db: DatabaseManager = Depends()):
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE registered_agents SET is_permitted = ? WHERE uuid = ?", (1 if permit else 0, agent_uuid))
    conn.commit()
    conn.close()
    return {"status": "ok", "agent_uuid": agent_uuid, "permitted": permit}

@router.get("/agents")
async def list_all_agents(db: DatabaseManager = Depends()):
    """Admin view: list ALL registered agents including non-permitted ones."""
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT uuid, ssh_host, ssh_username, is_permitted FROM registered_agents")
    rows = cursor.fetchall()
    conn.close()
    return {"agents": [{"uuid": r[0], "ssh_host": r[1], "ssh_username": r[2], "is_permitted": bool(r[3])} for r in rows]}
