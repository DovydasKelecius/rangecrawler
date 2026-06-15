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
                CREATE TABLE IF NOT EXISTS registered_agents (
                    uuid TEXT PRIMARY KEY,
                    registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    ssh_host TEXT,
                    ssh_port INTEGER,
                    ssh_username TEXT,
                    ssh_pkey_path TEXT,
                    ssh_host_key TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pending_handshakes (
                    agent_uuid TEXT PRIMARY KEY,
                    public_key TEXT,
                    challenge TEXT,
                    scope TEXT DEFAULT 'shell',
                    status TEXT DEFAULT 'pending',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
                    agent_uuid TEXT,
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
                    client_uuid TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    UNIQUE(client_uuid, model_id)
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

    def check_access(self, client_uuid: str, model_id: str) -> Optional[ClientPermission]:
        """Verify if a client UUID has a valid permission for a model."""
        conn = self.get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT client_uuid, model_id, is_active 
            FROM client_permissions 
            WHERE client_uuid = ? AND model_id = ? AND is_active = 1
        ''', (client_uuid, model_id))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return ClientPermission(
            client_uuid=row[0],
            model_id=row[1],
            is_active=bool(row[2])
        )

    def get_permitted_models(self, client_uuid: str) -> List[ModelConfig]:
        conn = self.get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT m.id, m.remote_url, m.ssh_host, m.ssh_username, m.ssh_pkey_path, m.description, m.is_active
            FROM models_registry m
            JOIN client_permissions p ON m.id = p.model_id
            WHERE p.client_uuid = ? AND p.is_active = 1 AND m.is_active = 1
        ''', (client_uuid,))
        rows = cursor.fetchall()
        conn.close()
        
        return [ModelConfig(
            id=r[0], remote_url=r[1], ssh_host=r[2], ssh_username=r[3], 
            ssh_pkey_path=r[4], description=r[5] or "", is_active=bool(r[6])
        ) for r in rows]

    def register_agent(self, agent_uuid: str, ssh_config: Optional[AgentWorkspaceConfig] = None) -> bool:
        try:
            conn = self.get_db()
            cursor = conn.cursor()
            if ssh_config:
                cursor.execute('''
                    INSERT INTO registered_agents (uuid, ssh_host, ssh_port, ssh_username, ssh_pkey_path, ssh_host_key)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(uuid) DO UPDATE SET
                        ssh_host=excluded.ssh_host, ssh_port=excluded.ssh_port, ssh_username=excluded.ssh_username,
                        ssh_pkey_path=excluded.ssh_pkey_path, ssh_host_key=excluded.ssh_host_key
                ''', (agent_uuid, ssh_config.ssh_host, ssh_config.ssh_port, ssh_config.ssh_username, ssh_config.ssh_pkey_path, ssh_config.ssh_host_key))
            else:
                cursor.execute("INSERT OR IGNORE INTO registered_agents (uuid) VALUES (?)", (agent_uuid,))
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False

    def is_agent_registered(self, agent_uuid: str) -> bool:
        conn = self.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT uuid FROM registered_agents WHERE uuid = ?", (agent_uuid,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def get_agent_config(self, agent_uuid: str) -> Optional[AgentWorkspaceConfig]:
        conn = self.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT ssh_host, ssh_port, ssh_username, ssh_pkey_path, ssh_host_key FROM registered_agents WHERE uuid = ? AND ssh_host IS NOT NULL", (agent_uuid,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return AgentWorkspaceConfig(
                agent_uuid=agent_uuid, ssh_host=row[0], ssh_port=row[1], ssh_username=row[2],
                ssh_pkey_path=row[3], ssh_host_key=row[4]
            )
        return None
