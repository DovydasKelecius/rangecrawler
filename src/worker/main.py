import httpx
import time
import os
import logging
import json
from dotenv import load_dotenv
from .services.ssh_manager import get_worker_pkey
from .services.inference import get_ollama_models
from .services.tasks import execute_remote_command, process_generation_request, handle_provisioning, cleanup_inactive_provisions

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - WORKER - %(message)s")
logger = logging.getLogger("OllamaWorker")

def register_worker_key(broker_url):
    pkey = get_worker_pkey()
    if not pkey:
        return
    pub_key = f"{pkey.get_name()} {pkey.get_base64()}"
    try:
        resp = httpx.post(f"{broker_url}/worker/register", json={"public_key": pub_key}, timeout=10.0)
        if resp.status_code == 200:
            logger.info("Worker public key registered with broker.")
    except Exception as e:
        logger.error(f"Failed to register key: {e}")

def worker_loop():
    broker_url = os.getenv("BROKER_URL", "http://localhost:8005")
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    
    logger.info(f"[READY] Worker connected to {broker_url}. Listening for prompts...")
    register_worker_key(broker_url)
    
    iteration = 0
    while True:
        try:
            if iteration % 60 == 0: # Report models every 5 minutes
                models = get_ollama_models(ollama_url)
                logger.debug(f"Found models: {models}")
                try:
                    httpx.post(
                        f"{broker_url}/worker/models", 
                        json={"models": [{"id": m, "remote_url": ollama_url} for m in models]}, 
                        timeout=5.0
                    )
                    if models:
                        logger.info(f"Refreshed {len(models)} models with broker.")
                except Exception as e:
                    logger.warning(f"Failed to report models: {e}")

            resp = httpx.get(f"{broker_url}/clients", timeout=10.0)
            if resp.status_code == 200:
                clients = resp.json().get("clients", [])
                if iteration % 10 == 0:
                    logger.info(f"Heartbeat: {len(clients)} registered clients.")
                
                for client in clients:
                    client_ip = client['ip']
                    logger.debug(f"Checking for tasks for {client_ip}...")
                    
                    # 1. Check for pending commands
                    cmd_resp = httpx.get(f"{broker_url}/command/pending/{client_ip}", timeout=10.0)
                    if cmd_resp.status_code == 200:
                        tasks = cmd_resp.json().get("commands", [])
                        if tasks:
                            logger.info(f"Found {len(tasks)} tasks for {client_ip}.")
                        for cmd in tasks:
                            execute_remote_command(client, cmd["id"], cmd["command"], broker_url)
                            try:
                                data = json.loads(cmd["command"])
                                if data.get("action") == "provision_isolated_ollama":
                                    handle_provisioning(client, data)
                            except Exception:
                                pass  # nosec
                    
                    # 2. Check for generation requests (Context Sync Loop)
                    process_generation_request(client, broker_url, ollama_url)
                
                cleanup_inactive_provisions()
            
            iteration += 1
        except Exception as e:
            logger.error(f"Worker Loop Error: {e}")
        
        time.sleep(5)

if __name__ == "__main__":
    worker_loop()
