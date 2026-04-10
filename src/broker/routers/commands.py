from fastapi import APIRouter, HTTPException, Depends, Request
from ..db.database import DatabaseManager

router = APIRouter(prefix="/command", tags=["commands"])

@router.post("/submit")
async def submit_command(request: Request, db: DatabaseManager = Depends()):
    body = await request.json()
    client_ip = body.get("client_ip")
    command = body.get("command")
    if not client_ip or not command:
        raise HTTPException(status_code=400, detail="Missing client_ip or command")
    
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO command_queue (client_ip, command) VALUES (?, ?)", (client_ip, command))
    command_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"status": "ok", "command_id": command_id}

@router.get("/pending/{client_ip}")
async def get_pending_commands(client_ip: str, db: DatabaseManager = Depends()):
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, command FROM command_queue WHERE client_ip = ? AND status = 'pending'", (client_ip,))
    rows = cursor.fetchall()
    conn.close()
    return {"commands": [{"id": r[0], "command": r[1]} for r in rows]}

@router.post("/result")
async def post_command_result(request: Request, db: DatabaseManager = Depends()):
    body = await request.json()
    command_id = body.get("command_id")
    result = body.get("result")
    
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE command_queue SET status = 'completed', result = ? WHERE id = ?", (result, command_id))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@router.get("/status/{command_id}")
async def get_command_status(command_id: int, db: DatabaseManager = Depends()):
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT status, result, command FROM command_queue WHERE id = ?", (command_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Command not found")
    return {"id": command_id, "status": row[0], "result": row[1], "command": row[2]}
