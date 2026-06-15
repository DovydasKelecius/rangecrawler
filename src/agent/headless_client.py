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

    def authorize_worker(self, public_key: str, temporary: bool = False):
        """Add the worker's public key to authorized_keys with strict permissions."""
        if not public_key:
            return
        
        try:
            ssh_dir = os.path.expanduser("~/.ssh")
            auth_keys_path = os.path.join(ssh_dir, "authorized_keys")
                
            # Ensure .ssh exists with 700
            if not os.path.exists(ssh_dir):
                os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
            
            # Zero Trust constraints
            restrictions = 'restrict,port-forwarding'
            entry = f'{restrictions} {public_key} # RangeCrawler Session'
            
            # Check if already exists
            if os.path.exists(auth_keys_path):
                with open(auth_keys_path, "r") as f:
                    if public_key in f.read():
                        return
            
            with open(auth_keys_path, "a") as f:
                f.write(f"\n{entry}\n")
            
            os.chmod(auth_keys_path, 0o600)
            print(f"[+] Authorized ephemeral key.")
            
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

    def run_heartbeat(self, interval: int = 60):
        """Keep the registration alive and poll for session handshakes."""
        print(f"[*] Starting heartbeat every {interval}s...")
        while True:
            try:
                # 1. Heartbeat
                httpx.post(f"{self.broker_url}/register", json={"agent_uuid": self.uuid}, timeout=5.0)
                
                # 2. Poll for handshakes
                resp = httpx.get(f"{self.broker_url}/handshake/poll/{self.uuid}", timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "pending":
                        pub_key = data.get("public_key")
                        print(f"[*] New session request. Authorizing ephemeral key...")
                        self.authorize_worker(pub_key, temporary=True)
                        httpx.post(f"{self.broker_url}/handshake/confirm", json={"agent_uuid": self.uuid}, timeout=5.0)
            except Exception as e: 
                logger.warning(f"Heartbeat/Handshake failed: {e}")
            time.sleep(interval)

def run_agent(broker: str, user: Optional[str] = None, ssh_port: int = 22, pkey: Optional[str] = None, heartbeat: bool = False):
    """Entry point for the RangeCrawler agent."""
    agent = RangeCrawlerAgent(broker, username=user)
    
    # 1. Self-Register
    if agent.register_self(ssh_port=ssh_port, pkey_path=pkey):
        # 2. If successful and heartbeat requested, stay alive
        if heartbeat:
            agent.run_heartbeat()
        else:
            print("[+] Done. Broker is now configured to use this machine.")
            return True
    else:
        return False

def main():
    parser = argparse.ArgumentParser(description="RangeCrawler Autonomous Agent")
    parser.add_argument("--broker", type=str, default="http://localhost:8005", help="URL of the RangeCrawler broker")
    parser.add_argument("--user", type=str, help="Username to register (default: current user)")
    parser.add_argument("--ssh-port", type=int, default=22, help="SSH port of this machine")
    parser.add_argument("--pkey", type=str, help="Path to the private key ON THE BROKER that accesses this machine")
    parser.add_argument("--heartbeat", action="store_true", help="Run in heartbeat mode to keep session alive")
    
    args = parser.parse_args()

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
