import httpx
import paramiko
import time
import os
import logging
import socket
import json

logging.basicConfig(level=logging.INFO, format="%(asctime)s - WORKER - %(message)s")
logger = logging.getLogger("OllamaWorker")

BROKER_URL = os.getenv("BROKER_URL", "http://localhost:8000")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

def fetch_context(ssh, remote_path):
    """Download context.json from the client."""
    logger.debug(f"Fetching context from {remote_path}")
    sftp = ssh.open_sftp()
    try:
        context_file = os.path.join(remote_path, "context.json")
        try:
            with sftp.open(context_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.info("context.json not found on client. Initializing new context.")
            return {"messages": []}
    except Exception as e:
        logger.error(f"Error fetching context: {e}")
        return {"messages": []}
    finally:
        sftp.close()

def push_context(ssh, remote_path, context):
    """Upload updated context.json to the client."""
    logger.debug(f"Pushing context to {remote_path}")
    sftp = ssh.open_sftp()
    try:
        context_file = os.path.join(remote_path, "context.json")
        with sftp.open(context_file, "w") as f:
            f.write(json.dumps(context, indent=2))
    except Exception as e:
        logger.error(f"Error pushing context: {e}")
    finally:
        sftp.close()

def call_ollama(model, messages):
    """Call the Ollama API for generation."""
    logger.info(f"Calling Ollama model {model}...")
    try:
        resp = httpx.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False
            },
            timeout=120.0
        )
        if resp.status_code == 200:
            return resp.json().get("message")
        else:
            logger.error(f"Ollama error: {resp.status_code} - {resp.text}")
            return None
    except Exception as e:
        logger.error(f"Failed to reach Ollama at {OLLAMA_URL}: {e}")
        return None

def process_generation_request(client_config, model="llama3"):
    """Full cycle: Connect -> Sync Context -> Generate -> Push Context."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    ssh_host = client_config["ssh_host"]
    ssh_user = client_config["ssh_username"]
    ssh_port = client_config.get("ssh_port", 22)
    remote_path = client_config.get("working_directory", ".")
    
    default_key = "/root/.ssh/id_rsa"
    pkey = None
    if os.path.exists(default_key):
        try:
            pkey = paramiko.RSAKey.from_private_key_file(default_key)
        except:
            pass

    try:
        # Optimization: Check if client even wants a generation before connecting?
        # For now, we still connect to check prompt.txt as per original requirement.
        logger.debug(f"Checking for generation request on {ssh_host}...")
        ssh.connect(
            hostname=ssh_host, 
            port=ssh_port, 
            username=ssh_user, 
            pkey=pkey, 
            timeout=5,
            banner_timeout=5
        )
        
        sftp = ssh.open_sftp()
        prompt = None
        prompt_file = os.path.join(remote_path, "prompt.txt")
        try:
            with sftp.open(prompt_file, "r") as f:
                prompt = f.read().strip()
            if prompt:
                logger.info(f"[PROMPT FOUND] on {ssh_host}")
                # Delete prompt file after reading to avoid re-processing
                sftp.remove(prompt_file)
        except FileNotFoundError:
            pass
        finally:
            sftp.close()

        if prompt:
            context = fetch_context(ssh, remote_path)
            context["messages"].append({"role": "user", "content": prompt})
            
            response_msg = call_ollama(model, context["messages"])
            if response_msg:
                context["messages"].append(response_msg)
                push_context(ssh, remote_path, context)
                logger.info(f"[SUCCESS] Context updated on {ssh_host}.")
        
        ssh.close()
    except Exception as e:
        logger.error(f"Generation cycle failed for {ssh_host}: {e}")

def execute_remote_command(client_config, command_id, command):
    """Execute a specific command via SSH and report results."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    pkey = None
    
    ssh_host = client_config["ssh_host"]
    ssh_user = client_config["ssh_username"]
    ssh_port = client_config.get("ssh_port", 22)
    
    default_key = "/root/.ssh/id_rsa"
    if os.path.exists(default_key):
        try:
            pkey = paramiko.RSAKey.from_private_key_file(default_key)
        except:
            pass

    try:
        logger.info(f"Connecting to {ssh_user}@{ssh_host} to run command {command_id}: {command}")
        ssh.connect(
            hostname=ssh_host, 
            port=ssh_port, 
            username=ssh_user, 
            pkey=pkey, 
            timeout=5,
            banner_timeout=5
        )
        
        stdin, stdout, stderr = ssh.exec_command(command)
        
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
        
        combined_result = f"STDOUT:\n{output}\nSTDERR:\n{error}"
        logger.info(f"[DONE] Command {command_id} finished on {ssh_host}.")
        
        # Report back to broker
        httpx.post(f"{BROKER_URL}/command/result", json={
            "command_id": command_id,
            "result": combined_result
        }, timeout=10.0)
        
        ssh.close()
        return True
    except Exception as e:
        err_msg = f"SSH/Execution Error on {ssh_host}: {e}"
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
    logger.info("Worker started in COMMAND + GENERATION mode.")
    register_worker_key()
    
    while True:
        try:
            # 1. Get all registered clients
            resp = httpx.get(f"{BROKER_URL}/clients", timeout=10.0)
            if resp.status_code == 200:
                clients = resp.json().get("clients", [])
                if not clients:
                    logger.debug("No clients registered.")
                
                for client in clients:
                    client_ip = client["ip"]
                    # 2. Check for pending commands
                    cmd_resp = httpx.get(f"{BROKER_URL}/command/pending/{client_ip}", timeout=10.0)
                    if cmd_resp.status_code == 200:
                        cmds = cmd_resp.json().get("commands", [])
                        if cmds:
                            logger.info(f"Found {len(cmds)} pending commands for {client_ip}")
                        for cmd in cmds:
                            execute_remote_command(client, cmd["id"], cmd["command"])
                    
                    # 3. Check for generation (Context Sync Loop)
                    process_generation_request(client)
            else:
                logger.error(f"Broker error: {resp.status_code}")
        except Exception as e:
            logger.error(f"Worker Loop Error: {e}")
        
        time.sleep(5)

if __name__ == "__main__":
    worker_loop()
