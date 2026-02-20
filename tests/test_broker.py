import pytest
from src.broker.manager import ModelManager
from src.broker.models import AppConfig, BrokerConfig, AgentConfig, AuthConfig
import os
from pathlib import Path

@pytest.fixture
def mock_config(tmp_path):
    db_path = tmp_path / "test.db"
    workspace = tmp_path / "workspace"
    return AppConfig(
        broker=BrokerConfig(database_path=str(db_path)),
        agent=AgentConfig(working_directory=str(workspace)),
        models=[],
        auth=AuthConfig(gemini_api_key="test_key")
    )

def test_manager_init(mock_config):
    manager = ModelManager(mock_config)
    assert manager.db_path == mock_config.broker.database_path
    assert os.path.exists(manager.db_path)

def test_ip_registration(mock_config):
    manager = ModelManager(mock_config)
    test_ip = "127.0.0.1"
    
    # First registration
    assert manager.register_ip(test_ip) is True
    assert manager.is_allowed(test_ip) is True
    
    # Duplicate registration
    assert manager.register_ip(test_ip) is False

def test_workspace_isolation(mock_config):
    manager = ModelManager(mock_config)
    test_ip = "192.168.1.1"
    
    workspace = manager.get_workspace_path(test_ip)
    assert workspace.exists()
    assert "agent_192-168-1-1" in str(workspace)
