import pytest
from fastapi.testclient import TestClient
from src.broker.main import app, db_manager
import sqlite3

@pytest.fixture(autouse=True)
def setup_teardown():
    # Setup: Ensure db_manager uses a test db if needed.
    # We should clean up tables before each test.
    conn = sqlite3.connect(db_manager.db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM allowed_ips")
    cursor.execute("DELETE FROM command_queue")
    cursor.execute("DELETE FROM worker_keys")
    cursor.execute("DELETE FROM client_permissions")
    conn.commit()
    conn.close()
    yield

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "online"

def test_register_ip():
    response = client.post("/register")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "ip" in data
    
    # Verify it's allowed now
    ip = data["ip"]
    assert db_manager.is_allowed(ip) is True

def test_unauthorized_access():
    # Try to access a protected route without registration
    # /v1/chat/completions requires registration
    response = client.post("/v1/chat/completions", json={"model": "test", "messages": []})
    assert response.status_code == 403

def test_command_flow():
    # 1. Register
    client.post("/register")
    
    # 2. Submit command
    submit_resp = client.post("/command/submit", json={
        "client_ip": "127.0.0.1",
        "command": "ls -la"
    })
    assert submit_resp.status_code == 200
    cmd_id = submit_resp.json()["command_id"]
    
    # 3. Get pending
    pending_resp = client.get("/command/pending/127.0.0.1")
    assert pending_resp.status_code == 200
    assert len(pending_resp.json()["commands"]) == 1
    
    # 4. Post result
    result_resp = client.post("/command/result", json={
        "command_id": cmd_id,
        "result": "file1\nfile2"
    })
    assert result_resp.status_code == 200
    
    # 5. Check status
    status_resp = client.get(f"/command/status/{cmd_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "completed"
    assert status_resp.json()["result"] == "file1\nfile2"
