import asyncio
import logging
import os
import json
import sqlite3
import shutil
from datetime import datetime
from typing import Dict, Set, Optional, List, Any
from pathlib import Path
from urllib.parse import urlparse
from sshtunnel import SSHTunnelForwarder

from .models import AppConfig, ModelConfig, SessionStats

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
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_directory",
            "description": "Get the current working directory name.",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

class LocalTools:
    """Implementation of tools scoped to an isolated workspace."""
    
    @staticmethod
    async def read_file(workspace_path: Path, path: str) -> str:
        try:
            # Security: Ensure the path is within the workspace
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
                return "Error: Access denied. Paths must be within your workspace."
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
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=workspace_path # Enforce workspace as cwd
            )
            try:
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
                return stdout.decode()
            except asyncio.TimeoutError:
                process.kill()
                return f"Error: Command timed out after {timeout} seconds."
        except Exception as e:
            return f"Error executing bash: {str(e)}"

class ModelManager:
    def __init__(self, config: AppConfig):
        self.config = config
        self.allowed_models: Dict[str, ModelConfig] = {m.id: m for m in config.models}
        self.sessions: Dict[str, SessionStats] = {}
        self.tunnels: Dict[str, SSHTunnelForwarder] = {}
        self.logger = logging.getLogger("ModelManager")
        self.db_path = config.broker.database_path
        self._init_db()
        
        # Base workspace directory
        self.workspace_base = Path(config.agent.working_directory).resolve()
        self.workspace_base.mkdir(parents=True, exist_ok=True)

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS allowed_ips (
                ip TEXT PRIMARY KEY,
                registered_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def get_workspace_path(self, ip: str) -> Path:
        """Create and return a persistent isolated directory for an IP."""
        # Normalize IP for safe folder name (replace : with _)
        safe_ip = ip.replace(":", "_").replace(".", "-")
        path = self.workspace_base / f"agent_{safe_ip}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def register_ip(self, ip: str) -> bool:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO allowed_ips (ip) VALUES (?)", (ip,))
            new_reg = cursor.rowcount > 0
            conn.commit()
            conn.close()
            
            if new_reg:
                self.sessions[ip] = SessionStats(ip=ip)
                # Initialize workspace
                self.get_workspace_path(ip)
                self.logger.info(f"Registered new IP persistently: {ip}")
            return new_reg
        except Exception as e:
            self.logger.error(f"Database error registering IP: {e}")
            return False

    def is_allowed(self, ip: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT ip FROM allowed_ips WHERE ip = ?", (ip,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def track_usage(self, ip: str, tokens: int = 0):
        if ip in self.sessions:
            session = self.sessions[ip]
            session.token_usage += tokens
            session.last_active = datetime.now()

    async def get_endpoint(self, model_id: str) -> str:
        if model_id not in self.allowed_models:
            raise ValueError(f"Model {model_id} not configured.")
        m_cfg = self.allowed_models[model_id]
        if m_cfg.ssh_host:
            return await self._get_ssh_tunnel_endpoint(m_cfg)
        return m_cfg.remote_url

    async def _get_ssh_tunnel_endpoint(self, m_cfg: ModelConfig) -> str:
        tunnel_key = f"{m_cfg.ssh_host}:{m_cfg.id}"
        if tunnel_key in self.tunnels:
            tunnel = self.tunnels[tunnel_key]
            if tunnel.is_active:
                return f"http://localhost:{tunnel.local_bind_port}"
            else:
                del self.tunnels[tunnel_key]

        parsed = urlparse(m_cfg.remote_url)
        remote_host = parsed.hostname or "localhost"
        remote_port = parsed.port or 8000
        
        tunnel = SSHTunnelForwarder(
            (m_cfg.ssh_host, 22),
            ssh_username=m_cfg.ssh_username,
            ssh_pkey=os.path.expanduser(m_cfg.ssh_pkey_path) if m_cfg.ssh_pkey_path else None,
            remote_bind_address=(remote_host, remote_port)
        )
        tunnel.start()
        self.tunnels[tunnel_key] = tunnel
        return f"http://localhost:{tunnel.local_bind_port}"

    def cleanup(self):
        for tunnel in self.tunnels.values():
            tunnel.stop()
        self.tunnels.clear()
