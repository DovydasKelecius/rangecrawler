import httpx
import paramiko
import time
import os
import logging
import socket

logging.basicConfig(level=logging.INFO, format="%(asctime)s - WORKER - %(message)s")
logger = logging.getLogger("OllamaWorker")

BROKER_URL = os.getenv("BROKER_URL", "http://localhost:8000")

def execute_remote_command(client_config, command_id, command):
    """Execute a specific command via SSH and report results."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    pkey = None
    
    ssh_host = client_config["ssh_host"]
    ssh_user = client_config["ssh_username"]
    ssh_port = client_config.get("ssh_port", 22)
    
    # Map the private key path to the container's volume
    default_key = "/root/.ssh/id_rsa"
    if os.path.exists(default_key):
        try:
            pkey = paramiko.RSAKey.from_private_key_file(default_key)
        except Exception as e:
            logger.error(f"Failed to load key: {e}")

    try:
        logger.info(f"Connecting to {ssh_user}@{ssh_host} to run: {command}")
        ssh.connect(hostname=ssh_host, port=ssh_port, username=ssh_user, pkey=pkey, timeout=5)
        
        stdin, stdout, stderr = ssh.exec_command(command)
        
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
        
        combined_result = f"STDOUT:\n{output}\nSTDERR:\n{error}"
        logger.info(f"[DONE] Command {command_id} finished.")
        
        # Report back to broker
        httpx.post(f"{BROKER_URL}/command/result", json={
            "command_id": command_id,
            "result": combined_result
        }, timeout=10.0)
        
        ssh.close()
        return True
    except Exception as e:
        err_msg = f"SSH/Execution Error: {e}"
        logger.error(err_msg)
        httpx.post(f"{BROKER_URL}/command/result", json={
            "command_id": command_id,
            "result": err_msg
        }, timeout=10.0)
        return False

def register_worker_key():
    """Read local public key and send it to the broker."""
    pub_key_path = "/root/.ssh/id_rsa.pub"
    if os.path.exists(pub_key_path):
        try:
            with open(pub_key_path, "r") as f:
                pub_key = f.read().strip()
            
            resp = httpx.post(f"{BROKER_URL}/worker/register", json={"public_key": pub_key}, timeout=10.0)
            if resp.status_code == 200:
                logger.info("[+] Registered worker public key with broker.")
            else:
                logger.error(f"[-] Failed to register worker key: {resp.status_code}")
        except Exception as e:
            logger.error(f"[-] Error registering worker key: {e}")

def worker_loop():
    logger.info("Worker started in COMMAND QUEUE mode.")
    register_worker_key()
    
    while True:
        try:
            # 1. Get all registered clients
            resp = httpx.get(f"{BROKER_URL}/clients", timeout=10.0)
            if resp.status_code == 200:
                clients = resp.json().get("clients", [])
                for client in clients:
                    # 2. Check for pending commands for THIS client
                    client_ip = client["ip"]
                    cmd_resp = httpx.get(f"{BROKER_URL}/command/pending/{client_ip}", timeout=10.0)
                    if cmd_resp.status_code == 200:
                        cmds = cmd_resp.json().get("commands", [])
                        for cmd in cmds:
                            execute_remote_command(client, cmd["id"], cmd["command"])
            else:
                logger.error(f"Broker error: {resp.status_code}")
        except Exception as e:
            logger.error(f"Worker Loop Error: {e}")
        
        time.sleep(5)

if __name__ == "__main__":
    worker_loop()
