import yaml
import os
import logging
from .models import AppConfig, BrokerConfig, ModelConfig

def load_config(path: str = "config.yaml") -> AppConfig:
    """Load and validate the broker configuration."""
    from typing import Dict, Any
    data: Dict[str, Any] = {}
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            logging.error(f"Error loading config from {path}: {e}")
    
    return AppConfig(
        broker=BrokerConfig(**data.get("broker", {})),
        models=[ModelConfig(**m) for m in data.get("models", [])],
        logging_level=data.get("logging", {}).get("level", "INFO")
    )
