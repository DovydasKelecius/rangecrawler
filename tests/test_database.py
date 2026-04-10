import pytest
import os
import sqlite3
from src.broker.db.database import DatabaseManager
from src.broker.models import AppConfig, BrokerConfig, ModelConfig, AgentConfig

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test.db"
    return str(db_file)

@pytest.fixture
def db_manager(temp_db, tmp_path):
    broker_cfg = BrokerConfig(database_path=temp_db)
    model_cfg = [ModelConfig(id="test-model", remote_url="http://localhost:11434")]
    agent_cfg = AgentConfig(working_directory=str(tmp_path / "workspaces"))
    
    app_cfg = AppConfig(
        broker=broker_cfg,
        models=model_cfg,
        agent=agent_cfg
    )
    return DatabaseManager(app_cfg)

def test_init_db(db_manager, temp_db):
    assert os.path.exists(temp_db)
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='allowed_ips'")
    assert cursor.fetchone() is not None
    conn.close()

def test_register_ip(db_manager):
    ip = "192.168.1.1"
    assert db_manager.register_ip(ip) is True
    assert db_manager.is_allowed(ip) is True
    assert db_manager.is_allowed("1.1.1.1") is False

def test_get_models(db_manager):
    models = db_manager.get_models()
    assert "test-model" in models
    assert models["test-model"].remote_url == "http://localhost:11434"

def test_check_access_no_permission(db_manager):
    ip = "10.0.0.1"
    assert db_manager.check_access(ip, "test-model") is None

def test_record_usage(db_manager):
    ip = "1.2.3.4"
    model_id = "test-model"
    db_manager.register_ip(ip)
    
    # Manually insert permission for testing
    conn = db_manager.get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO client_permissions (client_ip, model_id) VALUES (?, ?)", (ip, model_id))
    conn.commit()
    conn.close()
    
    db_manager.record_usage(ip, model_id, 100)
    permission = db_manager.check_access(ip, model_id)
    assert permission.used_seconds == 100
    assert permission.lease_start is not None
