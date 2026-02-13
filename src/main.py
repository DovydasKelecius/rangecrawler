import argparse
import uvicorn
import logging

def main():
    parser = argparse.ArgumentParser(description="RangeCrawler: Portable LLM Broker")
    parser.add_argument("--mode", type=str, default="broker", choices=["broker"], help="Mode to run in")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to config file")
    
    args = parser.parse_args()

    if args.mode == "broker":
        from src.broker.server import app, manager
        from src.broker.config import load_config
        
        # In this implementation, server.py already imports and loads config.
        # But we might want to override with the CLI arg:
        import src.broker.server as server_mod
        new_config = load_config(args.config)
        server_mod.manager.config = new_config.broker
        server_mod.manager.allowed_models = {m.id: m for m in new_config.models}
        
        uvicorn.run(app, host=new_config.broker.host, port=new_config.broker.port)

if __name__ == "__main__":
    main()
