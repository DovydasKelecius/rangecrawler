import os
import json
import logging
import httpx
import paramiko
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

def handle_provisioning(client_config, provision_data):
    client_ip = client_config["ip"]
    if client_ip in ACTIVE_PROVISIONS:
        prev = ACTIVE_PROVISIONS[client_ip]
        prev["proxy_proc"].terminate()
        prev["tunnel_proc"].terminate()
    
    proxy_port = 11435
    proxy_proc = subprocess.Popen([sys.executable, "src/worker/shield_proxy.py", "--port", str(proxy_port)])  # nosec
    tunnel_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes", "-N", "-R", f"{provision_data['target_port']}:localhost:{proxy_port}", f"{client_config['ssh_username']}@{client_config['ssh_host']}"]
    tunnel_proc = subprocess.Popen(tunnel_cmd)  # nosec
    
    ACTIVE_PROVISIONS[client_ip] = {"proxy_proc": proxy_proc, "tunnel_proc": tunnel_proc, "start_time": time.time()}

def cleanup_inactive_provisions():
    now = time.time()
    to_remove = [ip for ip, data in ACTIVE_PROVISIONS.items() if now - data["start_time"] > 3600]
    for ip in to_remove:
        data = ACTIVE_PROVISIONS.pop(ip)
        data["proxy_proc"].terminate()
        data["tunnel_proc"].terminate()
