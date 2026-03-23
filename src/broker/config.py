import yaml
import os
import logging
from dotenv import load_dotenv
from .models import AppConfig, BrokerConfig, ModelConfig, AgentConfig

def load_config(path: str = "config.yaml") -> AppConfig:
    """Load and validate the broker configuration, merging .env overrides."""
    # Load .env first to make os.getenv work for overrides
    load_dotenv()
    
    data: dict = {}
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            logging.error(f"Error loading config from {path}: {e}")
    
    # 1. Broker Config Overrides
    broker_data = data.get("broker", {})
    broker_cfg = BrokerConfig(
        host=os.getenv("BROKER_HOST", broker_data.get("host", "0.0.0.0")),
        port_assignment_url=os.getenv("BROKER_PORT_ASSIGNMENT_URL", broker_data.get("port_assignment_url")),
        default_port=int(os.getenv("BROKER_PORT", broker_data.get("default_port", 8005))),
        database_path=os.getenv("DATABASE_PATH", broker_data.get("database_path", "rangecrawler.db")),
        request_timeout=float(os.getenv("REQUEST_TIMEOUT", broker_data.get("request_timeout", 60.0)))
    )
    
    # 2. Agent Config Overrides
    agent_data = data.get("agent", {})
    agent_cfg = AgentConfig(
        enabled=bool(os.getenv("AGENT_ENABLED", agent_data.get("enabled", True))),
        max_iterations=int(os.getenv("AGENT_MAX_ITERATIONS", agent_data.get("max_iterations", 15))),
        default_timeout=int(os.getenv("AGENT_DEFAULT_TIMEOUT", agent_data.get("default_timeout", 30))),
        working_directory=os.getenv("AGENT_WORKING_DIR", agent_data.get("working_directory", "."))
    )
    
    # 3. Models and Global settings
    return AppConfig(
        broker=broker_cfg,
        agent=agent_cfg,
        models=[ModelConfig(**m) for m in data.get("models", [])],
        logging_level=os.getenv("LOG_LEVEL", data.get("logging", {}).get("level", "INFO"))
    )
