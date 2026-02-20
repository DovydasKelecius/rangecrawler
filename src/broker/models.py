from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime

class ModelConfig(BaseModel):
    id: str
    remote_url: str
    ssh_host: Optional[str] = None
    ssh_username: Optional[str] = None
    ssh_pkey_path: Optional[str] = None

class BrokerConfig(BaseModel):
    host: str = "0.0.0.0"
    port_assignment_url: Optional[str] = None
    default_port: int = 8000
    idle_timeout: int = 600

class AppConfig(BaseModel):
    broker: BrokerConfig
    models: List[ModelConfig]
    logging_level: str = "INFO"

class SessionStats(BaseModel):
    ip: str
    token_usage: int = 0
    start_time: datetime = Field(default_factory=datetime.now)
    last_active: datetime = Field(default_factory=datetime.now)
