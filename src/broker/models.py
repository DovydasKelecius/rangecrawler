from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class ModelConfig(BaseModel):
    id: str
    remote_url: str
    ssh_host: Optional[str] = None
    ssh_username: Optional[str] = None
    ssh_pkey_path: Optional[str] = None

class AgentConfig(BaseModel):
    enabled: bool = True
    max_iterations: int = 15
    default_timeout: int = 30
    working_directory: str = "."

class BrokerConfig(BaseModel):
    host: str = "0.0.0.0"
    port_assignment_url: Optional[str] = None
    default_port: int = 8000
    idle_timeout: int = 600
    check_interval: int = 60
    database_path: str = "rangecrawler.db"

class AuthConfig(BaseModel):
    gemini_api_key: Optional[str] = None

class AppConfig(BaseModel):
    broker: BrokerConfig
    models: List[ModelConfig]
    auth: AuthConfig = Field(default_factory=AuthConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    logging_level: str = "INFO"

class SessionStats(BaseModel):
    ip: str
    token_usage: int = 0
    start_time: datetime = Field(default_factory=datetime.now)
    last_active: datetime = Field(default_factory=datetime.now)
