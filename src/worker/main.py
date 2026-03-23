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
    if not pkey: return
    pub_key = f"{pkey.get_name()} {pkey.get_base64()}"
    try:
        logger.info(f"Registering worker key at {broker_url}/worker/register")
        resp = httpx.post(f"{broker_url}/worker/register", json={"public_key": pub_key}, timeout=10.0)
        logger.info(f"Worker key registration status: {resp.status_code}")
    except Exception as e:
        logger.error(f"Failed to register key at {broker_url}: {e}")

def worker_loop():
    broker_url = os.getenv("BROKER_URL", "http://localhost:8005")
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    
    logger.info(f"[READY] Worker connecting to Broker: {broker_url}, Ollama: {ollama_url}")
    register_worker_key(broker_url)
    
    iteration = 0
    while True:
        try:
            if iteration % 60 == 0:
                logger.info("Syncing models with broker...")
                models = get_ollama_models(ollama_url)
                logger.info(f"Found {len(models)} models on Ollama.")
                try:
                    resp = httpx.post(
                        f"{broker_url}/worker/models", 
                        json={"models": [{"id": m, "remote_url": ollama_url} for m in models]}, 
                        timeout=5.0
                    )
                    logger.info(f"Reported models to broker. Status: {resp.status_code}")
                except Exception as e:
                    logger.error(f"Error reporting models to broker at {broker_url}: {e}")

            logger.info(f"Polling broker for clients at {broker_url}/clients")
            resp = httpx.get(f"{broker_url}/clients", timeout=10.0)
            if resp.status_code == 200:
                clients = resp.json().get("clients", [])
                logger.info(f"Broker returned {len(clients)} clients.")
                for client in clients:
                    client_ip = client['ip']
                    logger.info(f"Checking commands for client {client_ip}")
                    # Commands
                    cmd_resp = httpx.get(f"{broker_url}/command/pending/{client_ip}", timeout=10.0)
                    if cmd_resp.status_code == 200:
                        cmds = cmd_resp.json().get("commands", [])
                        if cmds:
                            logger.info(f"Executing {len(cmds)} commands for {client_ip}")
                        for cmd in cmds:
                            execute_remote_command(client, cmd["id"], cmd["command"], broker_url)
                            try:
                                data = json.loads(cmd["command"])
                                if data.get("action") == "provision_isolated_ollama":
                                    handle_provisioning(client, data)
                            except: pass
                    
                    # Generation
                    logger.info(f"Processing generation requests for client {client_ip}")
                    process_generation_request(client, broker_url, ollama_url)
                
                cleanup_inactive_provisions()
            else:
                logger.error(f"Broker returned error status: {resp.status_code}")
            
            iteration += 1
        except Exception as e:
            logger.error(f"Worker Loop Global Error: {e}")
        
        logger.info("Sleeping for 5 seconds...")
        time.sleep(5)

if __name__ == "__main__":
    worker_loop()
