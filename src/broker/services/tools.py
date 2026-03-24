import os
import json
import shlex
import asyncio
import logging
import paramiko
from typing import Optional
from pathlib import Path
from ..models import AgentWorkspaceConfig

logger = logging.getLogger(__name__)

class LocalTools:
    """Implementation of tools scoped to an isolated local workspace."""
    
    @staticmethod
    async def read_file(workspace_path: Path, path: str) -> str:
        try:
            full_path = (workspace_path / path).resolve()
            if not str(full_path).startswith(str(workspace_path.resolve())):
                return "Error: Access denied. Paths must be within your workspace."
            return full_path.read_text(encoding='utf-8')
        except Exception as e:
            return f"Error reading file: {str(e)}"

    @staticmethod
    async def write_file(workspace_path: Path, path: str, content: str) -> str:
        try:
            full_path = (workspace_path / path).resolve()
            if not str(full_path).startswith(str(workspace_path.resolve())):
                return "Error: Access denied."
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding='utf-8')
            return f"Success: Wrote to {path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

    @staticmethod
    async def list_directory(workspace_path: Path, path: str = ".") -> str:
        try:
            full_path = (workspace_path / path).resolve()
            if not str(full_path).startswith(str(workspace_path.resolve())):
                return "Error: Access denied."
            items = os.listdir(full_path)
            return json.dumps(items)
        except Exception as e:
            return f"Error listing directory: {str(e)}"

    @staticmethod
    async def run_bash(workspace_path: Path, command: str, timeout: int = 30) -> str:
        try:
            process = await asyncio.create_subprocess_shell(
                command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, cwd=workspace_path
            )
            try:
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
                return stdout.decode()
            except asyncio.TimeoutError:
                process.kill()
                return "Error: Command timed out."
        except Exception as e:
            return f"Error executing bash: {str(e)}"

class RemoteTools:
    """Implementation of tools scoped to a remote machine via SSH."""
    
    @staticmethod
    def _get_ssh_client(config: AgentWorkspaceConfig) -> paramiko.SSHClient:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
        
        # Add host key if available
        if config.ssh_host_key:
            try:
                parts = config.ssh_host_key.split()
                if len(parts) >= 2:
                    import base64
                    key_type, key_str = parts[0], parts[1]
                    key_bytes = base64.b64decode(key_str)
                    key: Optional[paramiko.PKey] = None
                    if key_type == "ssh-rsa":
                        key = paramiko.RSAKey(data=key_bytes)
                    elif key_type == "ssh-ed25519":
                        key = paramiko.Ed25519Key(data=key_bytes)
                    else:
                        key = None
                    if key:
                        ssh.get_host_keys().add(config.ssh_host, key_type, key)
            except Exception as e:
                logger.warning(f"Failed to add host key: {e}")

        pkey = None
        if config.ssh_pkey_path:
            pkey = paramiko.RSAKey.from_private_key_file(os.path.expanduser(config.ssh_pkey_path))
        
        ssh.connect(hostname=config.ssh_host, port=config.ssh_port, username=config.ssh_username, pkey=pkey, timeout=10)
        return ssh

    @staticmethod
    async def read_file(config: AgentWorkspaceConfig, path: str) -> str:
        try:
            ssh = RemoteTools._get_ssh_client(config)
            sftp = ssh.open_sftp()
            full_path = os.path.join(config.working_directory, path)
            with sftp.open(full_path, 'r') as f:
                content = f.read().decode('utf-8')
            ssh.close()
            return content
        except Exception as e:
            return f"Error reading remote file: {str(e)}"

    @staticmethod
    async def write_file(config: AgentWorkspaceConfig, path: str, content: str) -> str:
        try:
            ssh = RemoteTools._get_ssh_client(config)
            sftp = ssh.open_sftp()
            full_path = os.path.join(config.working_directory, path)
            remote_dir = os.path.dirname(full_path)
            if remote_dir:
                ssh.exec_command(f"mkdir -p {shlex.quote(remote_dir)}")  # nosec
            with sftp.open(full_path, 'w') as f:
                f.write(content.encode('utf-8'))
            ssh.close()
            return f"Success: Wrote to {path}"
        except Exception as e:
            return f"Error writing remote file: {str(e)}"

    @staticmethod
    async def list_directory(config: AgentWorkspaceConfig, path: str = ".") -> str:
        try:
            ssh = RemoteTools._get_ssh_client(config)
            sftp = ssh.open_sftp()
            full_path = os.path.join(config.working_directory, path)
            items = sftp.listdir(full_path)
            ssh.close()
            return json.dumps(items)
        except Exception as e:
            return f"Error listing remote directory: {str(e)}"

    @staticmethod
    async def run_bash(config: AgentWorkspaceConfig, command: str, timeout: int = 30) -> str:
        try:
            ssh = RemoteTools._get_ssh_client(config)
            full_cmd = f"cd {shlex.quote(config.working_directory)} && {command}"
            stdin, stdout, stderr = ssh.exec_command(full_cmd, timeout=timeout)  # nosec
            output = stdout.read().decode() + stderr.read().decode()
            ssh.close()
            return output
        except Exception as e:
            return f"Error executing remote bash: {str(e)}"

# --- OpenAI-Compatible Tool Definitions ---
AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the content of a file from local disk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File name or relative path within your workspace."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with specific content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File name or relative path within your workspace."},
                    "content": {"type": "string", "description": "Full text content to write."}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and directories in your current workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path (default: '.')."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Execute a shell command in your workspace and return its output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The command to run."},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)."}
                },
                "required": ["command"]
            }
        }
    }
]
