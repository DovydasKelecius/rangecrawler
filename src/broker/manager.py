import asyncio
import logging
import httpx
from typing import Dict, Set, Optional
from datetime import datetime
from sshtunnel import SSHTunnelForwarder
import os
from urllib.parse import urlparse

from .models import AppConfig, ModelConfig, SessionStats

class ModelManager:
    """
    Manages remote vLLM endpoints, SSH tunnels, and IP whitelisting.
    """
    def __init__(self, config: AppConfig):
        self.config = config
        self.allowed_models: Dict[str, ModelConfig] = {m.id: m for m in config.models}
        self.allowed_ips: Set[str] = set()
        self.sessions: Dict[str, SessionStats] = {}
        self.tunnels: Dict[str, SSHTunnelForwarder] = {}
        self.logger = logging.getLogger("ModelManager")

    def register_ip(self, ip: str) -> bool:
        """Whitelist an IP and initialize session stats."""
        if ip not in self.allowed_ips:
            self.allowed_ips.add(ip)
            self.sessions[ip] = SessionStats(ip=ip)
            self.logger.info(f"Registered new IP: {ip}")
            return True
        return False

    def is_allowed(self, ip: str) -> bool:
        """Check if an IP is whitelisted."""
        return ip in self.allowed_ips

    def track_usage(self, ip: str, tokens: int = 0):
        """Update session stats (hook for future budgeting)."""
        if ip in self.sessions:
            session = self.sessions[ip]
            session.token_usage += tokens
            session.last_active = datetime.now()

    async def get_endpoint(self, model_id: str) -> str:
        """Return the target URL for the model, establishing SSH tunnels if needed."""
        if model_id not in self.allowed_models:
            raise ValueError(f"Model {model_id} not configured.")

        m_cfg = self.allowed_models[model_id]
        
        # If SSH is required but not yet active
        if m_cfg.ssh_host:
            return await self._get_ssh_tunnel_endpoint(m_cfg)
            
        return m_cfg.remote_url

    async def _get_ssh_tunnel_endpoint(self, m_cfg: ModelConfig) -> str:
        """Establish or reuse an SSH tunnel."""
        tunnel_key = f"{m_cfg.ssh_host}:{m_cfg.id}"
        if tunnel_key in self.tunnels:
            tunnel = self.tunnels[tunnel_key]
            # Verify if still active
            if tunnel.is_active:
                return f"http://localhost:{tunnel.local_bind_port}"
            else:
                self.logger.info(f"Tunnel for {m_cfg.id} is inactive, restarting...")
                del self.tunnels[tunnel_key]

        parsed = urlparse(m_cfg.remote_url)
        remote_host = parsed.hostname or "localhost"
        remote_port = parsed.port or 8000

        self.logger.info(f"Establishing SSH tunnel to {m_cfg.ssh_host} for {m_cfg.id}")
        
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
        """Stop all SSH tunnels."""
        for tunnel in self.tunnels.values():
            tunnel.stop()
        self.tunnels.clear()
