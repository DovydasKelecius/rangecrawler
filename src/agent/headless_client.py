import logging
import httpx
import socket
import os
import platform
import getpass
import argparse
import time
from typing import Optional

logger = logging.getLogger(__name__)

class RangeCrawlerAgent:
    def __init__(self, broker_url: str, working_dir: Optional[str] = None, username: Optional[str] = None):
        self.broker_url = broker_url.rstrip("/")
        self.working_dir = working_dir or os.getcwd()
        self.username = username or getpass.getuser()
        self.hostname = socket.gethostname()
        self.os_info = f"{platform.system()} {platform.release()}"
        
    def get_local_ip(self):
        """Try to find the IP address that can reach the broker."""
        # If broker is on localhost, we are likely the host talking to a docker container.
        # We should tell the broker to connect back to the Docker Gateway IP.
        if "127.0.0.1" in self.broker_url or "localhost" in self.broker_url:
            return "172.18.0.1" 

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Doesn't even have to be reachable
            s.connect(('8.8.8.8', 1))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip

    def authorize_worker(self, public_key: str):
        """Add the worker's public key to authorized_keys."""
        if not public_key:
            return
        
        # Use the actual home directory of the registration user
        if self.username == "root":
            auth_keys_path = "/root/.ssh/authorized_keys"
        else:
            auth_keys_path = os.path.expanduser("~/.ssh/authorized_keys")
            
        os.makedirs(os.path.dirname(auth_keys_path), exist_ok=True)
        
        # Check if already exists
        if os.path.exists(auth_keys_path):
            with open(auth_keys_path, "r") as f:
                if public_key in f.read():
                    print("[*] Worker key already authorized.")
                    return
        
        with open(auth_keys_path, "a") as f:
            f.write(f"\n{public_key}\n")
        
        os.chmod(auth_keys_path, 0o600)
        print(f"[+] Automatically authorized worker public key for user {self.username}.")

    def register_self(self, ssh_port: int = 22, pkey_path: Optional[str] = None):
        """Register this machine as a remote workspace on the broker."""
        local_ip = self.get_local_ip()
        print(f"[*] Identifying as {self.username}@{local_ip} ({self.os_info})")
        
        payload = {
            "ssh_host": local_ip,
            "ssh_port": ssh_port,
            "ssh_username": self.username,
            "ssh_pkey_path": pkey_path,
            "working_directory": self.working_dir
        }
        
        try:
            resp = httpx.post(f"{self.broker_url}/register/ssh", json=payload, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                print(f"[+] Successfully registered with broker at {self.broker_url}")
                print(f"[+] Workspace set to: {self.working_dir}")
                
                # Handle automatic key authorization
                worker_key = data.get("worker_public_key")
                if worker_key:
                    self.authorize_worker(worker_key)
                
                return True
            else:
                print(f"[-] Registration failed: {resp.text}")
                return False
        except Exception as e:
            print(f"[-] Error connecting to broker: {e}")
            return False

    def run_heartbeat(self, interval: int = 60):
        """Keep the registration alive."""
        print(f"[*] Starting heartbeat every {interval}s...")
        while True:
            try:
                httpx.post(f"{self.broker_url}/register", timeout=5.0)
            except Exception as e: 
                logger.warning(f"Registration failed: {e}")
            time.sleep(interval)

def main():
    parser = argparse.ArgumentParser(description="RangeCrawler Autonomous Agent")
    parser.add_argument("--broker", type=str, default="http://localhost:8000", help="URL of the RangeCrawler broker")
    parser.add_argument("--dir", type=str, help="Working directory for the LLM (default: current dir)")
    parser.add_argument("--user", type=str, help="Username to register (default: current user)")
    parser.add_argument("--ssh-port", type=int, default=22, help="SSH port of this machine")
    parser.add_argument("--pkey", type=str, help="Path to the private key ON THE BROKER that accesses this machine")
    parser.add_argument("--heartbeat", action="store_true", help="Run in heartbeat mode to keep session alive")
    
    args = parser.parse_args()

    agent = RangeCrawlerAgent(args.broker, args.dir, username=args.user)
    
    # 1. Self-Register
    if agent.register_self(ssh_port=args.ssh_port, pkey_path=args.pkey):
        # 2. If successful and heartbeat requested, stay alive
        if args.heartbeat:
            agent.run_heartbeat()
        else:
            print("[+] Done. Broker is now configured to use this machine.")
    else:
        exit(1)

if __name__ == "__main__":
    main()
