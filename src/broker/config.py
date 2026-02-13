import yaml
import os
from pydantic import BaseModel
from typing import List, Optional

class ModelConfig(BaseModel):
    id: str
    max_replicas: int = 1

class BrokerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    base_vllm_port: int = 8001
    idle_timeout: int = 600
    gpu_memory_utilization: float = 0.45
    max_replicas_per_model: int = 1
    check_interval: int = 60

class AppConfig(BaseModel):
    broker: BrokerConfig
    models: List[ModelConfig]
    logging_level: str = "INFO"

def load_config(path: str = "config.yaml") -> AppConfig:
    if not os.path.exists(path):
        # Return defaults if no config file
        return AppConfig(broker=BrokerConfig(), models=[])
    
    with open(path, "r") as f:
        data = yaml.safe_load(f)
        
    return AppConfig(
        broker=BrokerConfig(**data.get("broker", {})),
        models=[ModelConfig(**m) for m in data.get("models", [])],
        logging_level=data.get("logging", {}).get("level", "INFO")
    )
