import httpx
import time
import os
import logging
import json
import socket
from .services.ssh_manager import get_worker_pkey
from .services.inference import get_ollama_models
from .services.tasks import execute_remote_command, process_generation_request, handle_provisioning, cleanup_inactive_provisions

logging.basicConfig(level=logging.INFO, format="%(asctime)s - WORKER - %(message)s")
logger = logging.getLogger("OllamaWorker")

BROKER_URL = os.getenv("BROKER_URL", "http://localhost:8005")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

def register_worker_key():
    pkey = get_worker_pkey()
    if not pkey: return
    pub_key = f"{pkey.get_name()} {pkey.get_base64()}"
    try:
        httpx.post(f"{BROKER_URL}/worker/register", json={"public_key": pub_key}, timeout=10.0)
    except Exception as e:
        logger.error(f"Failed to register key: {e}")

def worker_loop():
    logger.info(f"[READY] Worker connected to {BROKER_URL}. Listening...")
    register_worker_key()
    
    iteration = 0
    while True:
        try:
            if iteration % 60 == 0:
                models = get_ollama_models(OLLAMA_URL)
                httpx.post(f"{BROKER_URL}/worker/models", json={"models": [{"id": m, "remote_url": OLLAMA_URL} for m in models]}, timeout=5.0)

            resp = httpx.get(f"{BROKER_URL}/clients", timeout=10.0)
            if resp.status_code == 200:
                clients = resp.json().get("clients", [])
                for client in clients:
                    # Commands
                    cmd_resp = httpx.get(f"{BROKER_URL}/command/pending/{client['ip']}", timeout=10.0)
                    if cmd_resp.status_code == 200:
                        for cmd in cmd_resp.json().get("commands", []):
                            execute_remote_command(client, cmd["id"], cmd["command"], BROKER_URL)
                            try:
                                data = json.loads(cmd["command"])
                                if data.get("action") == "provision_isolated_ollama":
                                    handle_provisioning(client, data)
                            except: pass
                    
                    # Generation
                    process_generation_request(client, BROKER_URL, OLLAMA_URL)
                
                cleanup_inactive_provisions()
            iteration += 1
        except Exception as e:
            logger.error(f"Worker Loop Error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    worker_loop()
