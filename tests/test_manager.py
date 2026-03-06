import pytest
import os
import sqlite3
from pathlib import Path
from src.broker.manager import ModelManager
from src.broker.models import AppConfig, BrokerConfig, ModelConfig, AgentConfig

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test.db"
    return str(db_file)

@pytest.fixture
def manager(temp_db, tmp_path):
    broker_cfg = BrokerConfig(database_path=temp_db)
    model_cfg = [ModelConfig(id="test-model", remote_url="http://localhost:11434")]
    agent_cfg = AgentConfig(working_directory=str(tmp_path / "workspaces"))
    
    app_cfg = AppConfig(
        broker=broker_cfg,
        models=model_cfg,
        agent=agent_cfg
    )
    return ModelManager(app_cfg)

def test_init_db(manager, temp_db):
    assert os.path.exists(temp_db)
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='allowed_ips'")
    assert cursor.fetchone() is not None
    conn.close()

def test_register_ip(manager):
    ip = "192.168.1.1"
    assert manager.register_ip(ip) is True
    assert manager.is_allowed(ip) is True
    assert manager.is_allowed("1.1.1.1") is False

def test_get_workspace_path(manager, tmp_path):
    ip = "10.0.0.1"
    path = manager.get_workspace_path(ip)
    assert isinstance(path, Path)
    assert "agent_10-0-0-1" in str(path)
    assert path.exists()

def test_track_usage(manager):
    ip = "1.2.3.4"
    manager.register_ip(ip)
    manager.track_usage(ip, tokens=500)
    assert manager.sessions[ip].token_usage == 500
