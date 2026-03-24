import os
import json
import logging
import paramiko
import shlex
from typing import Optional, Dict, Any

logger = logging.getLogger("WorkerSSH")

def get_worker_pkey():
    """Try to load the worker's private key, or generate one if missing."""
    key_paths = [
        ("/root/.ssh/id_ed25519", paramiko.Ed25519Key),
        ("/root/.ssh/id_rsa", paramiko.RSAKey),
        (os.path.expanduser("~/.ssh/id_ed25519"), paramiko.Ed25519Key),
        (os.path.expanduser("~/.ssh/id_rsa"), paramiko.RSAKey),
    ]
    
    for path, key_class in key_paths:
        if os.path.exists(path):
            try:
                key = key_class.from_private_key_file(path)
                return key
            except Exception as e:
                logger.debug(f"Failed to load key from {path}: {e}")

    # Generate new key
    logger.info("No SSH keys found. Generating a new RSA key pair...")
    new_key_path = os.path.expanduser("~/.ssh/id_rsa")
    os.makedirs(os.path.dirname(new_key_path), exist_ok=True)
    key = paramiko.RSAKey.generate(4096)
    key.write_private_key_file(new_key_path)
    with open(f"{new_key_path}.pub", "w") as f:
        f.write(f"{key.get_name()} {key.get_base64()}")
    return key

def setup_host_key(ssh: paramiko.SSHClient, host: str, host_key: Optional[str]):
    if not host_key:
        return
    try:
        parts = host_key.split()
        if len(parts) >= 2:
            import base64
            key_type, key_str = parts[0], parts[1]
            key_bytes = base64.b64decode(key_str)
            key: Optional[paramiko.PKey] = None
            if key_type == "ssh-rsa":
                key = paramiko.RSAKey(data=key_bytes)
            elif key_type == "ssh-ed25519":
                key = paramiko.Ed25519Key(data=key_bytes)
            elif key_type.startswith("ecdsa-sha2-"):
                key = paramiko.ECDSAKey(data=key_bytes)
            if key:
                ssh.get_host_keys().add(host, key_type, key)
    except Exception as e:
        logger.warning(f"Failed to load host key for {host}: {e}")

def fetch_context(ssh: paramiko.SSHClient, remote_path: str) -> Dict[str, Any]:
    sftp = ssh.open_sftp()
    try:
        context_file = os.path.join(remote_path, "context.json")
        try:
            with sftp.open(context_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, IOError):
            return {"messages": []}
    finally:
        sftp.close()

def push_context(ssh: paramiko.SSHClient, remote_path: str, context: Dict[str, Any]):
    sftp = ssh.open_sftp()
    try:
        context_file = os.path.join(remote_path, "context.json")
        with sftp.open(context_file, "w") as f:
            f.write(json.dumps(context, indent=2))
    finally:
        sftp.close()

def execute_remote_tool(ssh: paramiko.SSHClient, remote_path: str, func_name: str, func_args: Dict[str, Any]) -> str:
    try:
        sftp = ssh.open_sftp()
        try:
            if func_name == "read_file":
                full_path = os.path.join(remote_path, func_args.get("path", ""))
                with sftp.open(full_path, "r") as f:
                    return f.read().decode("utf-8")
            elif func_name == "write_file":
                full_path = os.path.join(remote_path, func_args.get("path", ""))
                content = func_args.get("content", "")
                remote_dir = os.path.dirname(full_path)
                if remote_dir:
                    ssh.exec_command(f"mkdir -p {shlex.quote(remote_dir)}")  # nosec
                with sftp.open(full_path, "w") as f:
                    f.write(content)
                return f"Success: Wrote to {func_args.get('path')}"
            elif func_name == "list_directory":
                full_path = os.path.join(remote_path, func_args.get("path", "."))
                return json.dumps(sftp.listdir(full_path))
            elif func_name == "run_bash":
                command = func_args.get("command", "")
                full_cmd = f"cd {shlex.quote(remote_path)} && {command}"
                _, stdout, stderr = ssh.exec_command(full_cmd, timeout=func_args.get("timeout", 30))  # nosec
                return stdout.read().decode() + stderr.read().decode()
        finally:
            sftp.close()
    except Exception as e:
        return f"Error executing tool {func_name}: {e}"
    return f"Error: Tool {func_name} not found."
