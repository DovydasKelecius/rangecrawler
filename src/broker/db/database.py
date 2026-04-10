import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from ..models import AppConfig, ModelConfig, ClientPermission, AgentWorkspaceConfig

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, config: Any):
        # We still expect it to be an AppConfig, but we use Any to hide it from FastAPI dependency parsing
        self.db_path = str(Path(config.broker.database_path).resolve())
        self._init_db(config)

    def get_db(self):
        """Returns a database connection."""
        return sqlite3.connect(self.db_path)

    def _init_db(self, config: AppConfig):
        db_file = Path(self.db_path)
        if db_file.is_dir():
            raise IsADirectoryError(f"Database path '{self.db_path}' is a directory.")
        
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
            
            # Sync models from config.yaml into DB
            for m in config.models:
                cursor.execute('''
                    INSERT OR IGNORE INTO models_registry (id, remote_url, ssh_host, ssh_username, ssh_pkey_path)
                    VALUES (?, ?, ?, ?, ?)
                ''', (m.id, m.remote_url, m.ssh_host, m.ssh_username, m.ssh_pkey_path))
            
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize database at {self.db_path}: {e}")
            raise

    def get_models(self) -> Dict[str, ModelConfig]:
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

        return ClientPermission(
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

    def record_usage(self, ip: str, model_id: str, duration_seconds: int):
        conn = self.get_db()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE client_permissions 
            SET used_seconds = used_seconds + ?,
                lease_start = CASE WHEN lease_start IS NULL THEN ? ELSE lease_start END
            WHERE client_ip = ? AND model_id = ?
        ''', (duration_seconds, datetime.now().isoformat(), ip, model_id))
        conn.commit()
        conn.close()

    def get_permitted_models(self, ip: str) -> List[ModelConfig]:
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
        
        return [ModelConfig(
            id=r[0], remote_url=r[1], ssh_host=r[2], ssh_username=r[3], 
            ssh_pkey_path=r[4], description=r[5] or "", is_active=bool(r[6])
        ) for r in rows]

    def register_ip(self, ip: str, ssh_config: Optional[AgentWorkspaceConfig] = None) -> bool:
        try:
            conn = self.get_db()
            cursor = conn.cursor()
            if ssh_config:
                cursor.execute('''
                    INSERT INTO allowed_ips (ip, ssh_host, ssh_port, ssh_username, ssh_pkey_path, ssh_host_key, working_directory)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ip) DO UPDATE SET
                        ssh_host=excluded.ssh_host, ssh_port=excluded.ssh_port, ssh_username=excluded.ssh_username,
                        ssh_pkey_path=excluded.ssh_pkey_path, ssh_host_key=excluded.ssh_host_key, working_directory=excluded.working_directory
                ''', (ip, ssh_config.ssh_host, ssh_config.ssh_port, ssh_config.ssh_username, ssh_config.ssh_pkey_path, ssh_config.ssh_host_key, ssh_config.working_directory))
            else:
                cursor.execute("INSERT OR IGNORE INTO allowed_ips (ip) VALUES (?)", (ip,))
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False

    def is_allowed(self, ip: str) -> bool:
        conn = self.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT ip FROM allowed_ips WHERE ip = ?", (ip,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def get_workspace_config(self, ip: str) -> Optional[AgentWorkspaceConfig]:
        conn = self.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT ssh_host, ssh_port, ssh_username, ssh_pkey_path, working_directory, ssh_host_key FROM allowed_ips WHERE ip = ? AND ssh_host IS NOT NULL", (ip,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return AgentWorkspaceConfig(
                client_ip=ip, ssh_host=row[0], ssh_port=row[1], ssh_username=row[2],
                ssh_pkey_path=row[3], working_directory=row[4] or ".", ssh_host_key=row[5]
            )
        return None
