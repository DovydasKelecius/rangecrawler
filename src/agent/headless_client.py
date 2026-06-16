import logging
import httpx
import socket
import os
import platform
import getpass
import argparse
import time
import subprocess # nosec B404
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class RangeCrawlerAgent:
    def __init__(self, broker_url: str, username: Optional[str] = None):
        self.broker_url = broker_url.rstrip("/")
        self.username = username or getpass.getuser()
        self.hostname = socket.gethostname()
        self.os_info = f"{platform.system()} {platform.release()}"
        self.uuid = self._get_or_create_uuid()

    def _get_or_create_uuid(self) -> str:
        """Read or generate a persistent unique ID for this agent."""
        import uuid
        uuid_path = os.path.join(os.path.expanduser("~"), ".rc_agent_id")
        if os.path.exists(uuid_path):
            try:
                with open(uuid_path, "r") as f:
                    return f.read().strip()
            except Exception:
                pass
        
        new_uuid = str(uuid.uuid4())
        try:
            with open(uuid_path, "w") as f:
                f.write(new_uuid)
        except Exception:
            pass
        return new_uuid
        
    def get_ssh_host_key(self) -> Optional[str]:
        """Read the local SSH host public key."""
        # Common locations for host keys, prioritized by modern standards
        key_paths = [
            "/etc/ssh/ssh_host_ed25519_key.pub",
            "/etc/ssh/ssh_host_rsa_key.pub",
            "/etc/ssh/ssh_host_ecdsa_key.pub"
        ]
        for path in key_paths:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        return f.read().strip()
                except Exception as e:
                    logger.debug(f"Failed to read host key from {path}: {e}")
        return None

    def get_local_ip(self):
        """Try to find the IP address that can reach the broker."""
        # If broker is on localhost, we are likely the host talking to a docker container.
        if "127.0.0.1" in self.broker_url or "localhost" in self.broker_url:
            try:
                route_cmd = ["ip", "route", "get", "1.1.1.1"]
                route_output = subprocess.check_output(route_cmd, stderr=subprocess.DEVNULL).decode() # nosec
                for part in route_output.split():
                    if part.startswith("172."):
                        return part
            except (subprocess.SubprocessError, IndexError):
                logger.debug("Failed to detect Docker gateway IP via ip route")
            
            return "172.18.0.1" 

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 1))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip

    def authorize_worker(self, public_key: str, temporary: bool = False, scope: str = "shell"):
        """Add the worker's public key to authorized_keys, replacing old keys for the same scope."""
        if not public_key:
            return
        
        try:
            ssh_dir = os.path.expanduser("~/.ssh")
            auth_keys_path = os.path.join(ssh_dir, "authorized_keys")
                
            # Ensure .ssh exists with 700
            if not os.path.exists(ssh_dir):
                os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
            
            # Zero Trust constraints based on scope
            if scope == "tunnel":
                restrictions = 'restrict,port-forwarding'
            else:
                restrictions = 'no-pty,no-X11-forwarding,no-agent-forwarding'
                
            new_entry = f'{restrictions} {public_key} # RangeCrawler Session ({scope})'
            
            lines = []
            if os.path.exists(auth_keys_path):
                with open(auth_keys_path, "r") as f:
                    for line in f:
                        # Remove old keys for the SAME scope to prevent duplication
                        if f"# RangeCrawler Session ({scope})" not in line:
                            lines.append(line)
            
            lines.append(new_entry + "\n")
            
            with open(auth_keys_path, "w") as f:
                f.writelines(lines)
            
            os.chmod(auth_keys_path, 0o600)
            print(f"[+] Authorized ephemeral key for {scope}.")
            
            if temporary:
                import threading
                def cleanup():
                    time.sleep(3600)
                    self.remove_worker_key(public_key)
                threading.Thread(target=cleanup, daemon=True).start()
        except Exception as e:
            print(f"[-] ERROR: Failed to authorize worker key: {e}")

    def remove_worker_key(self, public_key: str):
        """Remove a specific worker key from authorized_keys."""
        try:
            auth_keys_path = os.path.expanduser("~/.ssh/authorized_keys")
            if not os.path.exists(auth_keys_path):
                return
            
            with open(auth_keys_path, "r") as f:
                lines = f.readlines()
            
            with open(auth_keys_path, "w") as f:
                for line in lines:
                    if public_key not in line:
                        f.write(line)
            print(f"[*] Cleaned up session key.")
        except Exception as e:
            print(f"[-] Error cleaning up key: {e}")

    def register_self(self, ssh_port: int = 22, pkey_path: Optional[str] = None):
        """Register this machine as a remote workspace on the broker."""
        local_ip = self.get_local_ip()
        host_key = self.get_ssh_host_key()
        print(f"[*] Identifying as {self.username}@{local_ip} ({self.os_info})")
        print(f"[*] Agent UUID: {self.uuid}")
        
        payload = {
            "agent_uuid": self.uuid,
            "ssh_host": local_ip,
            "ssh_port": ssh_port,
            "ssh_username": self.username,
            "ssh_pkey_path": pkey_path,
            "ssh_host_key": host_key
        }
        
        try:
            resp = httpx.post(f"{self.broker_url}/register/ssh", json=payload, timeout=10.0)
            if resp.status_code == 200:
                print(f"[+] Successfully registered with broker at {self.broker_url}")
                return True
            else:
                print(f"[-] Registration failed: {resp.text}")
                return False
        except Exception as e:
            print(f"[-] Error connecting to broker: {e}")
            return False

    def run_heartbeat(self, interval: int = 600):
        """Keep the registration alive and poll for session handshakes."""
        print(f"[*] Starting heartbeat every {interval}s (Long-polling enabled)...")
        while True:
            try:
                # 1. Heartbeat (less frequent now)
                httpx.post(f"{self.broker_url}/register", json={"agent_uuid": self.uuid}, timeout=5.0)
                
                # 2. Long-poll for handshakes (waits on server)
                resp = httpx.get(f"{self.broker_url}/handshake/poll/{self.uuid}", timeout=35.0)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "pending":
                        pub_key = data.get("public_key")
                        scope = data.get("scope", "shell")
                        print(f"[*] New session request ({scope}). Authorizing ephemeral key...")
                        self.authorize_worker(pub_key, temporary=True, scope=scope)
                        httpx.post(f"{self.broker_url}/handshake/confirm", json={"agent_uuid": self.uuid}, timeout=5.0)
                
                # Wait a bit before next poll to be nice to the CPU, but not long because we want to be ready
                time.sleep(1)
            except Exception as e: 
                logger.warning(f"Heartbeat/Handshake failed: {e}")
                time.sleep(10) # Wait longer on error

    def check_status(self):
        """Check for active tunnels and session keys."""
        print(f"[*] Agent UUID: {self.uuid}")
        print(f"[*] Broker: {self.broker_url}")

        # 1. Check authorized_keys for RC sessions
        auth_keys = os.path.expanduser("~/.ssh/authorized_keys")
        sessions = []
        if os.path.exists(auth_keys):
            with open(auth_keys, "r") as f:
                for line in f:
                    if "RangeCrawler Session" in line:
                        sessions.append(line.strip())

        if sessions:
            print(f"[+] Active Sessions ({len(sessions)}):")
            for s in sessions:
                # Extract scope if possible
                scope = "unknown"
                if "(" in s and ")" in s:
                    scope = s.split("(")[-1].split(")")[0]
                print(f"    - {scope} session active")
        else:
            print("[-] No active session keys.")

        # 2. Check for reverse tunnels (ss -ntlp or netstat)
        try:
            # Look for local port 11434 being used by a reverse tunnel
            output = subprocess.check_output(["ss", "-ntlp"], stderr=subprocess.DEVNULL).decode()
            if "127.0.0.1:11434" in output:
                print("[+] Tunnel: Reverse tunnel to Ollama (11434) detected.")
            else:
                print("[-] Tunnel: No reverse tunnel on 11434.")
        except Exception:
            pass

def run_agent(broker: str, user: Optional[str] = None, ssh_port: int = 22, pkey: Optional[str] = None, heartbeat: bool = False):
    """Entry point for the RangeCrawler agent."""
    agent = RangeCrawlerAgent(broker, username=user)
    
    # 1. Self-Register
    if agent.register_self(ssh_port=ssh_port, pkey_path=pkey):
        # 2. If successful and heartbeat requested, stay alive
        if heartbeat:
            agent.run_heartbeat(interval=600)
        else:
            print("[+] Done. Broker is now configured to use this machine.")
            return True
    return False

    def list_remote_models(self):
        """Fetch whitelisted models from the worker via the reverse tunnel."""
        print(f"[*] Querying available models from tunnel (localhost:11434)...")
        try:
            resp = httpx.get("http://localhost:11434/api/tags", timeout=5.0)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                if not models:
                    print("[-] No models found on worker.")
                    return
                
                print(f"[+] Available Models ({len(models)}):")
                print(f"{'NAME':<20} | {'SIZE':<10} | {'MODIFIED'}")
                print("-" * 50)
                for m in models:
                    name = m.get("name", "unknown")
                    size_gb = m.get("size", 0) / (1024**3)
                    modified = m.get("modified_at", "unknown")[:10]
                    print(f"{name:<20} | {size_gb:>8.2f} GB | {modified}")
            else:
                print(f"[-] Failed to list models: {resp.status_code}")
                if resp.status_code == 403:
                    print("    (Access denied by Shield Proxy)")
        except Exception as e:
            print(f"[-] Error: Could not connect to local tunnel. Is the reverse tunnel active?")
            print(f"    Details: {e}")

def main():
    parser = argparse.ArgumentParser(description="RangeCrawler Autonomous Agent")
    parser.add_argument("--broker", type=str, default="http://localhost:8005", help="URL of the RangeCrawler broker")
    parser.add_argument("--user", type=str, help="Username to register (default: current user)")
    parser.add_argument("--ssh-port", type=int, default=22, help="SSH port of this machine")
    parser.add_argument("--pkey", type=str, help="Path to the private key ON THE BROKER that accesses this machine")
    parser.add_argument("--heartbeat", action="store_true", help="Run in heartbeat mode to keep session alive")
    parser.add_argument("--status", action="store_true", help="Check local agent and tunnel status")
    parser.add_argument("--models", action="store_true", help="List models available via the tunnel")
    
    args = parser.parse_args()

    agent = RangeCrawlerAgent(args.broker, username=args.user)

    if args.status:
        agent.check_status()
        return
    
    if args.models:
        agent.list_remote_models()
        return

    success = run_agent(
        broker=args.broker,
        user=args.user,
        ssh_port=args.ssh_port,
        pkey=args.pkey,
        heartbeat=args.heartbeat
    )
    if not success:
        exit(1)

if __name__ == "__main__":
    main()
