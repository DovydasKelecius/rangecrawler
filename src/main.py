import argparse
import uvicorn
import httpx
import logging
from src.broker.config import load_config

def get_dynamic_port(url: str | None, default: int) -> int:
    """Fetch the assigned port from an external registration service."""
    if not url:
        return default
    try:
        resp = httpx.get(url, timeout=5.0)
        if resp.status_code == 200:
            port = int(resp.json().get("port", default))
            logging.info(f"Dynamic port assigned: {port}")
            return port
    except Exception as e:
        logging.warning(f"Failed to fetch dynamic port from {url}: {e}. Using default {default}.")
    return default

def main():
    parser = argparse.ArgumentParser(description="RangeCrawler: Secure LLM Reverse Proxy")
    parser.add_argument("--mode", type=str, default="broker", choices=["broker"], help="Mode to run in")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to config file")
    
    args = parser.parse_args()

    # Load initial config
    config = load_config(args.config)
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, config.logging_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if args.mode == "broker":
        # 1. Fetch Dynamic Port
        listen_port = get_dynamic_port(
            config.broker.port_assignment_url, 
            config.broker.default_port
        )
        
        # 2. Start the Server
        # (server.py already initialized manager and app with current config)
        from src.broker.server import app, manager
        
        try:
            uvicorn.run(app, host=config.broker.host, port=listen_port)
        finally:
            # 3. Cleanup Tunnels
            manager.cleanup()

if __name__ == "__main__":
    main()
