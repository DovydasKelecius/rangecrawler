import logging
import os
from typing import Dict
from urllib.parse import urlparse
from sshtunnel import SSHTunnelForwarder
from ..models import ModelConfig

logger = logging.getLogger(__name__)

class TunnelManager:
    def __init__(self):
        self.tunnels: Dict[str, SSHTunnelForwarder] = {}

    async def get_endpoint(self, model_id: str, m_cfg: ModelConfig) -> str:
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
        logger.info(f"Started SSH tunnel for {m_cfg.id} on port {tunnel.local_bind_port}")
        return f"http://localhost:{tunnel.local_bind_port}"

    def cleanup(self):
        for tunnel in self.tunnels.values():
            tunnel.stop()
        self.tunnels.clear()
