import yaml
import os
import logging
from .models import AppConfig, BrokerConfig, ModelConfig, AuthConfig

def load_config(path: str = "config.yaml") -> AppConfig:
    """Load and validate the broker configuration.
    
    Priority:
    1. Environment Variable (GEMINI_API_KEY)
    2. config.yaml file
    3. None (auth fails)
    """
    from typing import Dict, Any
    data: Dict[str, Any] = {}
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            logging.error(f"Error loading config from {path}: {e}")
    
    # 1. Try environment variable first
    gemini_key = os.getenv("GEMINI_API_KEY")
    
    if gemini_key:
        logging.info("Using Gemini API key from environment variable.")
    else:
        # 2. Fallback to config file
        gemini_key = data.get("auth", {}).get("gemini_api_key")
        if gemini_key:
            logging.info(f"Using Gemini API key from {path}.")
        else:
            logging.warning("No Gemini API key found in environment or config file.")
    
    return AppConfig(
        broker=BrokerConfig(**data.get("broker", {})),
        models=[ModelConfig(**m) for m in data.get("models", [])],
        auth=AuthConfig(gemini_api_key=gemini_key),
        logging_level=data.get("logging", {}).get("level", "INFO")
    )
