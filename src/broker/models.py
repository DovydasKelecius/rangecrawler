from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class ModelConfig(BaseModel):
    id: str
    remote_url: str
    ssh_host: Optional[str] = None
    ssh_username: Optional[str] = None
    ssh_pkey_path: Optional[str] = None
    description: Optional[str] = ""
    is_active: bool = True

class ClientPermission(BaseModel):
    client_uuid: str
    model_id: str
    is_active: bool = True

class AgentWorkspaceConfig(BaseModel):
    agent_uuid: str
    ssh_host: str
    ssh_port: int = 22
    ssh_username: str
    ssh_pkey_path: Optional[str] = None
    ssh_host_key: Optional[str] = None

class AgentConfig(BaseModel):
    enabled: bool = True
    default_timeout: int = 30
    workspaces: List[AgentWorkspaceConfig] = Field(default_factory=list)

class BrokerConfig(BaseModel):
    host: str = "0.0.0.0"  # nosec B104
    port_assignment_url: Optional[str] = None
    default_port: int = 8005
    idle_timeout: int = 600
    check_interval: int = 60
    database_path: str = "rangecrawler.db"
    request_timeout: float = 60.0

class AppConfig(BaseModel):
    broker: BrokerConfig
    models: List[ModelConfig] = Field(default_factory=list)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    logging_level: str = "INFO"

class SessionStats(BaseModel):
    client_uuid: str
    token_usage: int = 0
    start_time: datetime = Field(default_factory=datetime.now)
    last_active: datetime = Field(default_factory=datetime.now)

class OllamaProvisionRequest(BaseModel):
    model: str
    timeout_minutes: int = 30
