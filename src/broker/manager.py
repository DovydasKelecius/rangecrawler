import asyncio
import logging
import os
import json
import sqlite3
import paramiko  # type: ignore[import-untyped]
import shlex
from datetime import datetime
from typing import Dict, Union, Optional, List
from pathlib import Path
from urllib.parse import urlparse
from sshtunnel import SSHTunnelForwarder # type: ignore[import-untyped]

from .models import AppConfig, ModelConfig, SessionStats, AgentWorkspaceConfig

logger = logging.getLogger(__name__)

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

class RemoteTools:
    """Implementation of tools scoped to a remote machine via SSH."""
    
    @staticmethod
    def _get_ssh_client(config: AgentWorkspaceConfig) -> paramiko.SSHClient:
        ssh = paramiko.SSHClient()
        
        # Strict policy: fail on unknown or changed host keys (recommended for security)
        ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
        
        # Optional: load system known_hosts file (usually ~/.ssh/known_hosts)
        ssh.load_system_host_keys()
        
        # Add host key if we have it
        if config.ssh_host_key:
            try:
                # Basic parsing: 'ssh-rsa AAAAB3Nza...'
                parts = config.ssh_host_key.split()
                if len(parts) >= 2:
                    key_type = parts[0]
                    key_str = parts[1]
                    
                    import base64
                    key_bytes = base64.b64decode(key_str)
                    
                    if key_type == "ssh-rsa":
                        key = paramiko.RSAKey(data=key_bytes)
                    elif key_type == "ssh-ed25519":
                        key = paramiko.Ed25519Key(data=key_bytes)
                    elif key_type.startswith("ecdsa-sha2-"):
                        key = paramiko.ECDSAKey(data=key_bytes)
                    else:
                        key = None
                    
                    if key:
                        ssh.get_host_keys().add(config.ssh_host, key_type, key)
            except Exception as e:
                logger.warning(f"Failed to manually add host key for {config.ssh_host}: {e}")
        
        pkey = None
        if config.ssh_pkey_path:
            try:
                pkey = paramiko.RSAKey.from_private_key_file(os.path.expanduser(config.ssh_pkey_path))
            except Exception as e:
                logger.error(f"Failed to load private key from {config.ssh_pkey_path}: {e}")
                raise
        
        try:
            ssh.connect(
                hostname=config.ssh_host,
                port=config.ssh_port,
                username=config.ssh_username,
                pkey=pkey,
                timeout=10
            )
            logger.info(f"SSH connection established to {config.ssh_host}:{config.ssh_port}")
            return ssh
        except paramiko.SSHException as e:
            logger.error(f"SSH connection failed to {config.ssh_host}: {e}")
            raise

    @staticmethod
    async def read_file(config: AgentWorkspaceConfig, path: str) -> str:
        try:
            ssh = RemoteTools._get_ssh_client(config)
            sftp = ssh.open_sftp()
            full_path = os.path.join(config.working_directory, path)
            with sftp.open(full_path, 'r') as f:
                content = f.read().decode('utf-8')
            sftp.close()
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
            # Create directories if needed
            remote_dir = os.path.dirname(full_path)
            if remote_dir:
                ssh.exec_command(f"mkdir -p {shlex.quote(remote_dir)}") # nosec
            
            with sftp.open(full_path, 'w') as f:
                f.write(content.encode('utf-8'))
            sftp.close()
            ssh.close()
            return f"Success: Wrote to {path} on remote machine."
        except Exception as e:
            return f"Error writing remote file: {str(e)}"

    @staticmethod
    async def list_directory(config: AgentWorkspaceConfig, path: str = ".") -> str:
        try:
            ssh = RemoteTools._get_ssh_client(config)
            sftp = ssh.open_sftp()
            full_path = os.path.join(config.working_directory, path)
            items = sftp.listdir(full_path)
            sftp.close()
            ssh.close()
            return json.dumps(items)
        except Exception as e:
            return f"Error listing remote directory: {str(e)}"

    @staticmethod
    async def run_bash(config: AgentWorkspaceConfig, command: str, timeout: int = 30) -> str:
        try:
            ssh = RemoteTools._get_ssh_client(config)
            full_cmd = f"cd {shlex.quote(config.working_directory)} && {command}"
            stdin, stdout, stderr = ssh.exec_command(full_cmd, timeout=timeout) # nosec
            output = stdout.read().decode() + stderr.read().decode()
            ssh.close()
            return output
        except Exception as e:
            return f"Error executing remote bash: {str(e)}"

class ModelManager:
    def __init__(self, config: AppConfig):
        self.config = config
        self.workspace_configs: Dict[str, AgentWorkspaceConfig] = {w.client_ip: w for w in config.agent.workspaces}
        self.sessions: Dict[str, SessionStats] = {}
        self.tunnels: Dict[str, SSHTunnelForwarder] = {}
        self.logger = logging.getLogger("ModelManager")
        
        # Ensure database path is absolute
        self.db_path = str(Path(config.broker.database_path).resolve())
        self._init_db()
        
        # Load models from DB
        self.allowed_models: Dict[str, ModelConfig] = self.get_models_from_db()
        
        # Base local workspace directory
        self.workspace_base = Path(config.agent.working_directory).resolve()
        self.workspace_base.mkdir(parents=True, exist_ok=True)

    def get_db(self):
        """Returns a database connection."""
        return sqlite3.connect(self.db_path)

    def register_models(self, models: List[ModelConfig]):
        """Register or update models reported by a worker."""
        conn = self.get_db()
        cursor = conn.cursor()
        for model in models:
            cursor.execute('''
                INSERT INTO models_registry (id, remote_url, ssh_host, ssh_username, ssh_pkey_path, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(id) DO UPDATE SET
                    remote_url=excluded.remote_url,
                    ssh_host=excluded.ssh_host,
                    ssh_username=excluded.ssh_username,
                    ssh_pkey_path=excluded.ssh_pkey_path,
                    is_active=1
            ''', (model.id, model.remote_url, model.ssh_host, model.ssh_username, model.ssh_pkey_path))
            self.logger.info(f"Registered model to DB: {model.id} -> {model.remote_url}")
        conn.commit()
        conn.close()
        # Refresh in-memory for immediate use
        self.allowed_models = self.get_models_from_db()

    def _init_db(self):
        db_file = Path(self.db_path)
        if db_file.is_dir():
            raise IsADirectoryError(
                f"Database path '{self.db_path}' is a directory, but a file is expected.\n"
                "FIX: On your VM host, run 'mkdir -p data' and ensure config.yaml has "
                "database_path: \"data/rangecrawler.db\""
            )
        
        # Ensure parent directory exists
        db_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            conn = self.get_db()
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS allowed_ips (
                    ip TEXT PRIMARY KEY,
                    registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    ssh_host TEXT,
                    ssh_port INTEGER,
                    ssh_username TEXT,
                    ssh_pkey_path TEXT,
                    ssh_host_key TEXT,
                    working_directory TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS worker_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    public_key TEXT,
                    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS command_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_ip TEXT,
                    command TEXT,
                    status TEXT DEFAULT 'pending',
                    result TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # --- New Tables for Permissions & Model Registry ---
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS models_registry (
                    id TEXT PRIMARY KEY,
                    remote_url TEXT NOT NULL,
                    ssh_host TEXT,
                    ssh_port INTEGER DEFAULT 22,
                    ssh_username TEXT,
                    ssh_pkey_path TEXT,
                    description TEXT,
                    is_active INTEGER DEFAULT 1
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS client_permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_ip TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    allow_tools INTEGER DEFAULT 1,
                    max_usage_seconds INTEGER,
                    used_seconds INTEGER DEFAULT 0,
                    expires_at DATETIME,
                    window_start TEXT,
                    window_end TEXT,
                    lease_start DATETIME,
                    lease_duration INTEGER,
                    is_active INTEGER DEFAULT 1,
                    UNIQUE(client_ip, model_id)
                )
            ''')
            
            conn.commit()
            
            # --- Auto-Migration: Sync models from config.yaml into DB ---
            for m in self.config.models:
                cursor.execute('''
                    INSERT OR IGNORE INTO models_registry (id, remote_url, ssh_host, ssh_username, ssh_pkey_path)
                    VALUES (?, ?, ?, ?, ?)
                ''', (m.id, m.remote_url, m.ssh_host, m.ssh_username, m.ssh_pkey_path))
            
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            self.logger.error(f"Failed to initialize database at {self.db_path}: {e}")
            raise

    def get_models_from_db(self) -> Dict[str, ModelConfig]:
        """Fetch all active models from the database."""
        conn = self.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, remote_url, ssh_host, ssh_username, ssh_pkey_path, description, is_active FROM models_registry WHERE is_active = 1")
        rows = cursor.fetchall()
        conn.close()
        
        return {
            row[0]: ModelConfig(
                id=row[0],
                remote_url=row[1],
                ssh_host=row[2],
                ssh_username=row[3],
                ssh_pkey_path=row[4],
                description=row[5] or "",
                is_active=bool(row[6])
            ) for row in rows
        }

    def check_access(self, ip: str, model_id: str) -> Optional[ClientPermission]:
        """Verify if a client IP has a valid permission for a model."""
        conn = self.get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT client_ip, model_id, allow_tools, max_usage_seconds, used_seconds, 
                   expires_at, window_start, window_end, lease_start, lease_duration, is_active 
            FROM client_permissions 
            WHERE client_ip = ? AND model_id = ? AND is_active = 1
        ''', (ip, model_id))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        perm = ClientPermission(
            client_ip=row[0],
            model_id=row[1],
            allow_tools=bool(row[2]),
            max_usage_seconds=row[3],
            used_seconds=row[4],
            expires_at=datetime.fromisoformat(row[5]) if row[5] else None,
            window_start=row[6],
            window_end=row[7],
            lease_start=datetime.fromisoformat(row[8]) if row[8] else None,
            lease_duration=row[9]
        )

        now = datetime.now()
        
        # 1. Absolute Expiration
        if perm.expires_at and now > perm.expires_at:
            return None
        
        # 2. Daily Window (Server Time)
        if perm.window_start and perm.window_end:
            now_time = now.strftime("%H:%M")
            if not (perm.window_start <= now_time <= perm.window_end):
                return None
        
        # 3. Quota (used seconds)
        if perm.max_usage_seconds is not None and perm.used_seconds >= perm.max_usage_seconds:
            return None
            
        # 4. Lease Duration
        if perm.lease_start and perm.lease_duration:
            if (now - perm.lease_start).total_seconds() > perm.lease_duration:
                return None

        return perm

    def record_usage(self, ip: str, model_id: str, duration_seconds: int):
        """Update wall-clock usage for a client-model pair."""
        conn = self.get_db()
        cursor = conn.cursor()
        
        # If this is the first usage, record lease_start
        cursor.execute('''
            UPDATE client_permissions 
            SET used_seconds = used_seconds + ?,
                lease_start = CASE WHEN lease_start IS NULL THEN ? ELSE lease_start END
            WHERE client_ip = ? AND model_id = ?
        ''', (duration_seconds, datetime.now().isoformat(), ip, model_id))
        
        conn.commit()
        conn.close()

    def get_permitted_models(self, ip: str) -> List[ModelConfig]:
        """List models that the client is actually permitted to use."""
        conn = self.get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT m.id, m.remote_url, m.ssh_host, m.ssh_username, m.ssh_pkey_path, m.description, m.is_active
            FROM models_registry m
            JOIN client_permissions p ON m.id = p.model_id
            WHERE p.client_ip = ? AND p.is_active = 1 AND m.is_active = 1
        ''', (ip,))
        rows = cursor.fetchall()
        conn.close()
        
        models = []
        for row in rows:
            mid = row[0]
            if self.check_access(ip, mid):
                models.append(ModelConfig(
                    id=row[0],
                    remote_url=row[1],
                    ssh_host=row[2],
                    ssh_username=row[3],
                    ssh_pkey_path=row[4],
                    description=row[5] or "",
                    is_active=bool(row[6])
                ))
        return models

    def get_workspace_context(self, ip: str) -> Union[Path, AgentWorkspaceConfig]:
        """Return either a local Path or a remote AgentWorkspaceConfig."""
        # 1. Check in-memory config (from yaml)
        if ip in self.workspace_configs:
            return self.workspace_configs[ip]
        
        # 2. Check Database for dynamically registered SSH workspaces
        conn = self.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT ssh_host, ssh_port, ssh_username, ssh_pkey_path, working_directory, ssh_host_key FROM allowed_ips WHERE ip = ? AND ssh_host IS NOT NULL", (ip,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return AgentWorkspaceConfig(
                client_ip=ip,
                ssh_host=row[0],
                ssh_port=row[1],
                ssh_username=row[2],
                ssh_pkey_path=row[3],
                working_directory=row[4] or ".",
                ssh_host_key=row[5]
            )
        
        # 3. Default to local persistent workspace
        safe_ip = ip.replace(":", "_").replace(".", "-")
        path = self.workspace_base / f"agent_{safe_ip}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_workspace_path(self, ip: str) -> Path:
        """DEPRECATED: Use get_workspace_context instead. Returns local path only."""
        safe_ip = ip.replace(":", "_").replace(".", "-")
        path = self.workspace_base / f"agent_{safe_ip}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def register_ip(self, ip: str, ssh_config: Optional[AgentWorkspaceConfig] = None) -> bool:
        try:
            conn = self.get_db()
            cursor = conn.cursor()
            
            if ssh_config:
                cursor.execute('''
                    INSERT INTO allowed_ips (ip, ssh_host, ssh_port, ssh_username, ssh_pkey_path, ssh_host_key, working_directory)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ip) DO UPDATE SET
                        ssh_host=excluded.ssh_host,
                        ssh_port=excluded.ssh_port,
                        ssh_username=excluded.ssh_username,
                        ssh_pkey_path=excluded.ssh_pkey_path,
                        ssh_host_key=excluded.ssh_host_key,
                        working_directory=excluded.working_directory
                ''', (ip, ssh_config.ssh_host, ssh_config.ssh_port, ssh_config.ssh_username, ssh_config.ssh_pkey_path, ssh_config.ssh_host_key, ssh_config.working_directory))
            else:
                cursor.execute("INSERT OR IGNORE INTO allowed_ips (ip) VALUES (?)", (ip,))
            
            new_reg = cursor.rowcount > 0
            conn.commit()
            conn.close()
            
            if new_reg or ssh_config:
                self.sessions[ip] = SessionStats(ip=ip)
                # Initialize local workspace (even if remote exists, as fallback)
                self.get_workspace_path(ip)
                self.logger.info(f"Registered IP {ip} (SSH: {ssh_config is not None})")
            return True
        except Exception as e:
            self.logger.error(f"Database error registering IP: {e}")
            return False

    def is_allowed(self, ip: str) -> bool:
        conn = self.get_db()
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
        # Refresh from DB to ensure we have the latest
        models = self.get_models_from_db()
        if model_id not in models:
            raise ValueError(f"Model {model_id} not configured or inactive.")
        m_cfg = models[model_id]
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
