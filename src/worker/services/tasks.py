import os
import json
import logging
import httpx
import paramiko  # type: ignore
import shlex
import sys
import subprocess  # nosec
import time
from typing import Dict, Any

from .ssh_manager import setup_host_key, get_worker_pkey, fetch_context, push_context
from .inference import worker_agent_loop

logger = logging.getLogger("WorkerTasks")

def execute_remote_command(client_config, command_id, command, broker_url):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    setup_host_key(ssh, client_config["ssh_host"], client_config.get("ssh_host_key"))
    pkey = get_worker_pkey()
    try:
        full_command = f"cd {shlex.quote(client_config.get('working_directory', '.'))} && {command}"
        ssh.connect(hostname=client_config["ssh_host"], port=client_config.get("ssh_port", 22), username=client_config["ssh_username"], pkey=pkey, timeout=10)
        _, stdout, stderr = ssh.exec_command(full_command)  # nosec
        result = f"STDOUT:\n{stdout.read().decode()}\nSTDERR:\n{stderr.read().decode()}"
        httpx.post(f"{broker_url}/command/result", json={"command_id": command_id, "result": result}, timeout=10.0)
        return True
    except Exception as e:
        httpx.post(f"{broker_url}/command/result", json={"command_id": command_id, "result": f"Error: {e}"}, timeout=10.0)
        return False
    finally:
        ssh.close()

def process_generation_request(client_config, broker_url, ollama_url):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    setup_host_key(ssh, client_config["ssh_host"], client_config.get("ssh_host_key"))
    pkey = get_worker_pkey()
    try:
        ssh.connect(hostname=client_config["ssh_host"], port=client_config.get("ssh_port", 22), username=client_config["ssh_username"], pkey=pkey, timeout=10)
        sftp = ssh.open_sftp()
        instruction = None
        remote_path = client_config.get("working_directory", ".")
        instr_file = os.path.join(remote_path, "instruction.json")
        try:
            with sftp.open(instr_file, "r") as f:
                instruction = json.loads(f.read().decode("utf-8"))
            sftp.remove(instr_file)
        except Exception:
            pass  # nosec

        if instruction:
            context = fetch_context(ssh, remote_path)
            context["messages"].append({"role": "user", "content": instruction["prompt"]})
            response_msg = worker_agent_loop(ssh, remote_path, instruction["model"], context["messages"], ollama_url)
            if response_msg:
                context["messages"].append(response_msg)
                push_context(ssh, remote_path, context)
                httpx.post(f"{broker_url}/chat/context/{client_config['ip']}", json=context, timeout=5.0)
    finally:
        ssh.close()

ACTIVE_PROVISIONS: Dict[str, Any] = {}

from .ssh_manager import setup_host_key, create_ephemeral_key, fetch_context, push_context

def handle_provisioning(client_config, provision_data, broker_url):
    agent_uuid = provision_data["agent_uuid"]
    if agent_uuid in ACTIVE_PROVISIONS:
        prev = ACTIVE_PROVISIONS[agent_uuid]
        prev["proxy_proc"].terminate()
        prev["tunnel_proc"].terminate()
    
    # 1. Generate Ephemeral Key
    pkey = create_ephemeral_key()
    pub_key = f"{pkey.get_name()} {pkey.get_base64()}"
    
    # 2. Handshake Phase 1 & 2: Init via Broker
    logger.info(f"Initiating handshake for agent {agent_uuid}")
    resp = httpx.post(f"{broker_url}/handshake/init", json={"agent_uuid": agent_uuid, "public_key": pub_key}, timeout=10.0)
    if resp.status_code != 200:
        logger.error(f"Handshake init failed: {resp.text}")
        return
    
    # 3. Wait for Handshake Phase 3: Agent Confirmation
    for _ in range(60): # 60s timeout
        v_resp = httpx.get(f"{broker_url}/handshake/verify/{agent_uuid}")
        if v_resp.json().get("status") == "confirmed":
            break
        time.sleep(1)
    else:
        logger.error("Handshake confirmation timeout.")
        return

    # 4. Connection Phase: Establish Tunnel
    proxy_port = 11435
    proxy_proc = subprocess.Popen([sys.executable, "src/worker/shield_proxy.py", "--port", str(proxy_port)])  # nosec
    
    # Use ephemeral key for SSH
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        pkey.write_private_key(f)
        key_path = f.name
    
    tunnel_cmd = [
        "ssh", "-i", key_path,
        "-o", "StrictHostKeyChecking=no", 
        "-o", "BatchMode=yes", 
        "-N", "-R", f"{provision_data['target_port']}:localhost:{proxy_port}", 
        f"{client_config['ssh_username']}@{client_config['ssh_host']}"
    ]
    tunnel_proc = subprocess.Popen(tunnel_cmd)  # nosec
    
    # Cleanup temp key file after spawn (process keeps it in memory or we can delete after connect)
    # Actually, keep it for now or use Paramiko for the tunnel to avoid disk
    
    ACTIVE_PROVISIONS[agent_uuid] = {"proxy_proc": proxy_proc, "tunnel_proc": tunnel_proc, "start_time": time.time(), "key_path": key_path}

def cleanup_inactive_provisions():
    now = time.time()
    to_remove = [ip for ip, data in ACTIVE_PROVISIONS.items() if now - data["start_time"] > 3600]
    for ip in to_remove:
        data = ACTIVE_PROVISIONS.pop(ip)
        data["proxy_proc"].terminate()
        data["tunnel_proc"].terminate()
