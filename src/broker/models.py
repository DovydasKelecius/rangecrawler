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
    client_ip: str
    model_id: str
    allow_tools: bool = True
    # Timing (Hybrid)
    max_usage_seconds: Optional[int] = None  # Total quota
    used_seconds: int = 0                    # Accumulated wall-clock time
    expires_at: Optional[datetime] = None    # Absolute deadline
    window_start: Optional[str] = None       # Daily start (e.g. "14:00")
    window_end: Optional[str] = None         # Daily end (e.g. "16:00")
    lease_start: Optional[datetime] = None   # First request timestamp
    lease_duration: Optional[int] = None     # Seconds from lease_start
    is_active: bool = True

class AgentWorkspaceConfig(BaseModel):
    client_ip: str
    ssh_host: str
    ssh_port: int = 22
    ssh_username: str
    ssh_pkey_path: Optional[str] = None
    ssh_host_key: Optional[str] = None
    working_directory: str = "."

class AgentConfig(BaseModel):
    enabled: bool = True
    max_iterations: int = 15
    default_timeout: int = 30
    working_directory: str = "."
    workspaces: List[AgentWorkspaceConfig] = Field(default_factory=list)

class BrokerConfig(BaseModel):
    host: str = "0.0.0.0"  # nosec B104
    port_assignment_url: Optional[str] = None
    default_port: int = 8000
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
    ip: str
    token_usage: int = 0
    start_time: datetime = Field(default_factory=datetime.now)
    last_active: datetime = Field(default_factory=datetime.now)

class OllamaProvisionRequest(BaseModel):
    model: str
    timeout_minutes: int = 30
