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

from .ssh_manager import setup_host_key, create_ephemeral_key, fetch_context, push_context
from .inference import worker_agent_loop

logger = logging.getLogger("WorkerTasks")

ACTIVE_PROVISIONS: Dict[str, Any] = {}
SESSION_KEYS: Dict[str, Any] = {}

import tempfile

def get_ssh_session(agent_config, broker_url, scope="shell"):
    agent_uuid = agent_config["uuid"]
    session_id = f"{agent_uuid}_{scope}"
    # Check if we already have a confirmed session for THIS scope
    if session_id in SESSION_KEYS:
        return SESSION_KEYS[session_id]
    
    logger.info(f"Establishing {scope} session for {agent_uuid}")
    pkey = create_ephemeral_key()
    pub_key = f"{pkey.get_name()} {pkey.get_base64()}"
    
    try:
        resp = httpx.post(f"{broker_url}/handshake/init", json={"agent_uuid": agent_uuid, "public_key": pub_key, "scope": scope}, timeout=10.0)
        if resp.status_code != 200:
            return None
        
        # Long-poll for verification (broker waits 30s)
        try:
            v_resp = httpx.get(f"{broker_url}/handshake/verify/{agent_uuid}", timeout=35.0)
            if v_resp.status_code == 200 and v_resp.json().get("status") == "confirmed":
                with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                    pkey.write_private_key_file(f.name)
                    key_path = f.name
                SESSION_KEYS[session_id] = {"pkey": pkey, "path": key_path}
                return SESSION_KEYS[session_id]
        except httpx.ReadTimeout:
            pass # Expected if not confirmed yet
    except Exception as e:
        logger.error(f"Handshake error: {e}")
    return None

def execute_remote_command(agent_config, command_id, command, broker_url):
    session = get_ssh_session(agent_config, broker_url, scope="shell")
    if not session:
        return False
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    setup_host_key(ssh, agent_config["ssh_host"], agent_config.get("ssh_host_key"))
    
    try:
        full_command = f"cd {shlex.quote(agent_config.get('working_directory', '.'))} && {command}"
        ssh.connect(hostname=agent_config["ssh_host"], port=agent_config.get("ssh_port", 22), username=agent_config["ssh_username"], pkey=session["pkey"], timeout=10)
        _, stdout, stderr = ssh.exec_command(full_command)  # nosec
        result = f"STDOUT:\n{stdout.read().decode()}\nSTDERR:\n{stderr.read().decode()}"
        httpx.post(f"{broker_url}/command/result", json={"command_id": command_id, "result": result}, timeout=10.0)
        return True
    except Exception as e:
        httpx.post(f"{broker_url}/command/result", json={"command_id": command_id, "result": f"Error: {e}"}, timeout=10.0)
        return False
    finally:
        ssh.close()

def process_generation_request(agent_config, broker_url, ollama_url):
    agent_uuid = agent_config["uuid"]
    session = get_ssh_session(agent_config, broker_url, scope="shell")
    if not session:
        return
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    setup_host_key(ssh, agent_config["ssh_host"], agent_config.get("ssh_host_key"))
    try:
        ssh.connect(hostname=agent_config["ssh_host"], port=agent_config.get("ssh_port", 22), username=agent_config["ssh_username"], pkey=session["pkey"], timeout=10)
        sftp = ssh.open_sftp()
        instruction = None
        remote_path = agent_config.get("working_directory", ".")
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
                httpx.post(f"{broker_url}/chat/context/{agent_uuid}", json=context, timeout=5.0)
    except Exception as e:
        logger.error(f"Generation error for {agent_uuid}: {e}")
    finally:
        ssh.close()

def handle_provisioning(agent_config, provision_data, broker_url):
    agent_uuid = agent_config["uuid"]
    
    # Check if already active and alive
    if agent_uuid in ACTIVE_PROVISIONS:
        data = ACTIVE_PROVISIONS[agent_uuid]
        if data["proxy_proc"].poll() is None and data["tunnel_proc"].poll() is None:
            return # Already running and healthy
        
        # Cleanup dead/stale processes
        try:
            data["proxy_proc"].terminate()
            data["tunnel_proc"].terminate()
        except Exception:
            pass
    
    # Provisions need tunnel scope
    session = get_ssh_session(agent_config, broker_url, scope="tunnel")
    if not session:
        return # Handshake probably not confirmed yet

    proxy_port = 11435
    logger.info(f"Starting Shield Proxy on {proxy_port} for {agent_uuid}")
    proxy_proc = subprocess.Popen([sys.executable, "src/worker/shield_proxy.py", "--port", str(proxy_port)])  # nosec
    
    tunnel_cmd = [
        "ssh", "-v", "-i", session["path"],
        "-o", "StrictHostKeyChecking=no", 
        "-o", "BatchMode=yes", 
        "-N", "-R", f"{provision_data['target_port']}:localhost:{proxy_port}", 
        f"{agent_config['ssh_username']}@{agent_config['ssh_host']}"
    ]
    logger.info(f"Starting Tunnel: {' '.join(tunnel_cmd)}")
    tunnel_proc = subprocess.Popen(tunnel_cmd)  # nosec
    
    ACTIVE_PROVISIONS[agent_uuid] = {"proxy_proc": proxy_proc, "tunnel_proc": tunnel_proc, "start_time": time.time(), "key_path": session["path"]}

def cleanup_inactive_provisions():
    now = time.time()
    to_remove = [uuid for uuid, data in ACTIVE_PROVISIONS.items() if now - data["start_time"] > 3600]
    for uuid in to_remove:
        data = ACTIVE_PROVISIONS.pop(uuid)
        data["proxy_proc"].terminate()
        data["tunnel_proc"].terminate()
