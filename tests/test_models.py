from src.broker.models import ModelConfig, AgentWorkspaceConfig, AppConfig, BrokerConfig, AuthConfig, AgentConfig

def test_model_config_creation():
    config = ModelConfig(id="test-model", remote_url="http://localhost:11434")
    assert config.id == "test-model"
    assert config.remote_url == "http://localhost:11434"
    assert config.ssh_host is None

def test_agent_workspace_config_defaults():
    config = AgentWorkspaceConfig(
        client_ip="127.0.0.1",
        ssh_host="localhost",
        ssh_username="user"
    )
    assert config.ssh_port == 22
    assert config.working_directory == "."

def test_app_config_nesting():
    broker = BrokerConfig()
    model = ModelConfig(id="m1", remote_url="http://url")
    auth = AuthConfig()
    agent = AgentConfig()
    
    app_cfg = AppConfig(
        broker=broker,
        models=[model],
        auth=auth,
        agent=agent
    )
    assert len(app_cfg.models) == 1
    assert app_cfg.broker.database_path == "rangecrawler.db"
