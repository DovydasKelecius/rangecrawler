import yaml
import os
import logging
from .models import AppConfig, BrokerConfig, ModelConfig

def load_config(path: str = "config.yaml") -> AppConfig:
    """Load and validate the broker configuration from YAML."""
    if not os.path.exists(path):
        logging.warning(f"Config file {path} not found. Using defaults.")
        return AppConfig(broker=BrokerConfig(), models=[])
    
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
            
        return AppConfig(
            broker=BrokerConfig(**data.get("broker", {})),
            models=[ModelConfig(**m) for m in data.get("models", [])],
            logging_level=data.get("logging", {}).get("level", "INFO")
        )
    except Exception as e:
        logging.error(f"Error loading config from {path}: {e}")
        return AppConfig(broker=BrokerConfig(), models=[])
