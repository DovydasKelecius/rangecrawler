import httpx
import paramiko  # type: ignore[import-untyped]
import time
import os
import logging
import json
import socket

logging.basicConfig(level=logging.INFO, format="%(asctime)s - WORKER - %(message)s")
logger = logging.getLogger("OllamaWorker")

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

# Suppress noisy library logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("paramiko").setLevel(logging.WARNING)

BROKER_URL = os.getenv("BROKER_URL", "http://localhost:8005")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

def get_effective_broker_url():
    """Return the broker URL, prioritizing ENV, then config.yaml, then state file."""
    # 1. Check environment variable
    env_url = os.getenv("BROKER_URL")
    if env_url and "localhost" not in env_url and "127.0.0.1" not in env_url:
        return env_url
    
    # 2. Check config.yaml (if it exists)
    config_path = os.environ.get("RANGECRAWLER_CONFIG", "config.yaml")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                import yaml
                data = yaml.safe_load(f)
                broker_cfg = data.get("broker", {})
                host = broker_cfg.get("host", "localhost")
                # If host is 0.0.0.0, we can't use it as a target
                if host == "0.0.0.0":
                    host = "localhost"
                port = broker_cfg.get("default_port", 8005)
                return f"http://{host}:{port}"
        except Exception:
            pass

    # 3. Check state file
    state_path = os.path.expanduser("~/.rangecrawler_state.json")
    if os.path.exists(state_path):
        try:
            with open(state_path, "r") as f:
                state = json.load(f)
                return state.get("broker_url", "http://localhost:8005")
        except Exception:
            pass
            
    return "http://localhost:8005"

def get_worker_pkey():
    """Try to load the worker's private key, or generate one if missing."""
    key_paths = [
        ("/root/.ssh/id_ed25519", paramiko.Ed25519Key),
        ("/root/.ssh/id_rsa", paramiko.RSAKey),
        (os.path.expanduser("~/.ssh/id_ed25519"), paramiko.Ed25519Key),
        (os.path.expanduser("~/.ssh/id_rsa"), paramiko.RSAKey),
    ]
    
    for path, key_class in key_paths:
        if os.path.exists(path):
            try:
                key = key_class.from_private_key_file(path)
                logger.debug(f"Loaded worker private key from {path}")
                return key
            except Exception as e:
                logger.debug(f"Failed to load key from {path}: {e}")

    # No key found? Generate a new one (RSA is the most compatible fallback)
    logger.info("No SSH keys found. Generating a new RSA key pair...")
    new_key_path = "/root/.ssh/id_rsa"
    try:
        os.makedirs(os.path.dirname(new_key_path), exist_ok=True)
        key = paramiko.RSAKey.generate(4096)
        key.write_private_key_file(new_key_path)
        # Also write the public key file for consistency
        with open(f"{new_key_path}.pub", "w") as f:
            f.write(f"{key.get_name()} {key.get_base64()}")
        logger.info(f"Successfully generated and saved new RSA key to {new_key_path}")
        return key
    except Exception as e:
        logger.error(f"Failed to generate worker key: {e}")
        return None

def fetch_context(ssh, remote_path):
    """Download context.json from the client."""
    logger.debug(f"Fetching context from {remote_path}")
    sftp = ssh.open_sftp()
    try:
        context_file = os.path.join(remote_path, "context.json")
        try:
            with sftp.open(context_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, IOError):
            logger.info("context.json not found on client. Creating new empty context.")
            new_context = {"messages": []}
            # Create the file immediately so it exists for further use
            with sftp.open(context_file, "w") as f:
                f.write(json.dumps(new_context, indent=2))
            return new_context
    except Exception as e:
        logger.error(f"Error fetching context: {e}")
        return {"messages": []}
    finally:
        sftp.close()

def push_context(ssh, remote_path, context):
    """Upload updated context.json to the client."""
    logger.debug(f"Pushing context to {remote_path}")
    sftp = ssh.open_sftp()
    try:
        context_file = os.path.join(remote_path, "context.json")
        with sftp.open(context_file, "w") as f:
            f.write(json.dumps(context, indent=2))
    except Exception as e:
        logger.error(f"Error pushing context: {e}")
    finally:
        sftp.close()

def setup_host_key(ssh, host, host_key):
    """Add a host key to the SSH client's in-memory store."""
    if not host_key:
        logger.debug(f"No host key provided for {host}")
        return
    
    try:
        parts = host_key.split()
        if len(parts) >= 2:
            key_type = parts[0]
            key_str = parts[1]
            import base64
            key_bytes = base64.b64decode(key_str)
            
            key = None
            if key_type == "ssh-rsa":
                key = paramiko.RSAKey(data=key_bytes)
            elif key_type == "ssh-ed25519":
                key = paramiko.Ed25519Key(data=key_bytes)
            elif key_type.startswith("ecdsa-sha2-"):
                key = paramiko.ECDSAKey(data=key_bytes)
            
            if key:
                # Add to in-memory store. This satisfies RejectPolicy for this session.
                ssh.get_host_keys().add(host, key_type, key)
                logger.debug(f"Loaded host key for {host} into memory ({key_type})")
    except Exception as e:
        logger.warning(f"Failed to load host key for {host}: {e}")

def execute_worker_tool(ssh, remote_path, func_name, func_args):
    """Execute a tool on the client via the existing SSH connection."""
    import shlex
    try:
        if func_name == "read_file":
            path = func_args.get("path")
            sftp = ssh.open_sftp()
            try:
                full_path = os.path.join(remote_path, path)
                with sftp.open(full_path, "r") as f:
                    return f.read().decode("utf-8")
            finally:
                sftp.close()
        
        elif func_name == "write_file":
            path = func_args.get("path")
            content = func_args.get("content")
            sftp = ssh.open_sftp()
            try:
                full_path = os.path.join(remote_path, path)
                # Create directories
                remote_dir = os.path.dirname(full_path)
                if remote_dir:
                    ssh.exec_command(f"mkdir -p {shlex.quote(remote_dir)}")
                with sftp.open(full_path, "w") as f:
                    f.write(content)
                return f"Success: Wrote to {path}"
            finally:
                sftp.close()

        elif func_name == "list_directory":
            path = func_args.get("path", ".")
            sftp = ssh.open_sftp()
            try:
                full_path = os.path.join(remote_path, path)
                return json.dumps(sftp.listdir(full_path))
            finally:
                sftp.close()

        elif func_name == "run_bash":
            command = func_args.get("command")
            timeout = func_args.get("timeout", 30)
            full_cmd = f"cd {shlex.quote(remote_path)} && {command}"
            stdin, stdout, stderr = ssh.exec_command(full_cmd, timeout=timeout)
            return stdout.read().decode() + stderr.read().decode()

        return f"Error: Tool {func_name} not implemented in worker."
    except Exception as e:
        return f"Error executing {func_name}: {e}"

def call_ollama(model, messages, tools=None):
    """Call the Ollama API for generation."""
    logger.info(f"Calling Ollama model {model}...")
    payload = {
        "model": model,
        "messages": messages,
        "stream": False
    }
    if tools:
        payload["tools"] = tools

    try:
        resp = httpx.post(
            f"{OLLAMA_URL}/api/chat",
            json=payload,
            timeout=120.0
        )
        if resp.status_code == 200:
            return resp.json().get("message")
        else:
            logger.error(f"Ollama error: {resp.status_code} - {resp.text}")
            return None
    except Exception as e:
        logger.error(f"Failed to reach Ollama at {OLLAMA_URL}: {e}")
        return None

def get_ollama_models():
    """Fetch available models from the local Ollama instance."""
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            model_names = [m["name"] for m in models]
            logger.debug(f"Fetched {len(model_names)} models from Ollama: {model_names}")
            return model_names
        else:
            logger.error(f"Ollama tags error: {resp.status_code}")
    except Exception as e:
        logger.warning(f"Could not fetch models from Ollama at {OLLAMA_URL}: {e}")
    return []

def worker_agent_loop(ssh, remote_path, model, messages):
    """Run the recursive agent loop locally on the worker."""
    current_messages = list(messages)
    max_iterations = 10
    
    for iteration in range(max_iterations):
        turn = iteration + 1
        logger.info(f"[THINKING] Turn {turn}/{max_iterations} using {model}...")
        
        response_msg = call_ollama(model, current_messages, tools=AGENT_TOOLS)
        if not response_msg:
            return None
            
        current_messages.append(response_msg)
        
        if "tool_calls" in response_msg and response_msg["tool_calls"]:
            for tool_call in response_msg["tool_calls"]:
                func_name = tool_call["function"]["name"]
                func_args = tool_call["function"]["arguments"]
                
                logger.info(f"[TOOL CALL] {func_name}({func_args})")
                result = execute_worker_tool(ssh, remote_path, func_name, func_args)
                logger.info(f"[TOOL RESULT] {func_name} execution finished.")
                
                current_messages.append({
                    "role": "tool",
                    "content": str(result)
                })
            # Loop again to give the model the tool results
            continue
        else:
            # Final text response
            content = response_msg.get("content", "")
            logger.info(f"[ANSWER] Agent session complete. Output: {content[:100]}...")
            return response_msg
            
    return {"role": "assistant", "content": "Error: Max iterations reached in worker agent loop."}

def process_generation_request(client_config, model="llama3"):
    """Full cycle: Connect -> Sync Context -> Generate -> Push Context."""
    if not client_config:
        logger.error("process_generation_request called with None client_config")
        return
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.load_system_host_keys()
    
    ssh_host = client_config["ssh_host"]
    ssh_user = client_config["ssh_username"]
    ssh_port = client_config.get("ssh_port", 22)
    remote_path = client_config.get("working_directory", ".")
    host_key = client_config.get("ssh_host_key")
    
    setup_host_key(ssh, ssh_host, host_key)
    
    pkey = get_worker_pkey()

    try:
        # Connect silently (DEBUG level only)
        logger.debug(f"Connecting to {ssh_host} to check for prompts...")
        ssh.connect(
            hostname=ssh_host, 
            port=ssh_port, 
            username=ssh_user, 
            pkey=pkey, 
            timeout=5,
            banner_timeout=5,
            allow_agent=True,
            look_for_keys=True
        )
        
        sftp = ssh.open_sftp()
        prompt = None
        try:
            # CD into the remote workspace to find prompt.txt
            ssh.exec_command(f"mkdir -p {remote_path}") # Ensure it exists
            prompt_file = os.path.join(remote_path, "prompt.txt")
            
            try:
                with sftp.open(prompt_file, "r") as f:
                    prompt = f.read().strip()
                if prompt:
                    logger.info(f"[RECEIVED] New prompt from {ssh_host}: \"{prompt[:50]}...\"")
                    sftp.remove(prompt_file)
            except (FileNotFoundError, IOError):
                pass
        finally:
            sftp.close()

        if prompt:
            context = fetch_context(ssh, remote_path)
            context["messages"].append({"role": "user", "content": prompt})
            
            # Run the full agent loop locally on the worker
            response_msg = worker_agent_loop(ssh, remote_path, model, context["messages"])
            
            if response_msg:
                context["messages"].append(response_msg)
                push_context(ssh, remote_path, context)
                
                # Push to broker cache so CLI can see it instantly
                try:
                    httpx.post(f"{BROKER_URL}/chat/context/{client_config['ip']}", json=context, timeout=5.0)
                except Exception as e:
                    logger.warning(f"Failed to push context to broker: {e}")
        
    except Exception as e:
        logger.error(f"Generation cycle failed for {ssh_host}: {e}")
    finally:
        ssh.close()

def execute_remote_command(client_config, command_id, command):
    """Execute a specific command via SSH and report results."""
    if not client_config:
        logger.error(f"execute_remote_command called with None client_config for command {command_id}")
        return False
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.load_system_host_keys()
    pkey = None
    
    ssh_host = client_config["ssh_host"]
    ssh_user = client_config["ssh_username"]
    ssh_port = client_config.get("ssh_port", 22)
    host_key = client_config.get("ssh_host_key")
    
    setup_host_key(ssh, ssh_host, host_key)
    
    pkey = get_worker_pkey()

    try:
        import shlex
        # Always CD into the workspace before running the command
        full_command = f"cd {shlex.quote(client_config.get('working_directory', '.'))} && {command}"
        
        logger.debug(f"Connecting to {ssh_user}@{ssh_host} to run command {command_id}")
        ssh.connect(
            hostname=ssh_host, 
            port=ssh_port, 
            username=ssh_user, 
            pkey=pkey, 
            timeout=5,
            banner_timeout=5,
            allow_agent=True,
            look_for_keys=True
        )
        
        stdin, stdout, stderr = ssh.exec_command(full_command) # nosec
        
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
        
        combined_result = f"STDOUT:\n{output}\nSTDERR:\n{error}"
        logger.debug(f"[DONE] Command {command_id} finished on {ssh_host}.")
        
        # Report back to broker
        httpx.post(f"{BROKER_URL}/command/result", json={
            "command_id": command_id,
            "result": combined_result
        }, timeout=10.0)
        
        return True
    except Exception as e:
        err_msg = f"SSH/Execution Error on {ssh_host}: {e}"
        logger.error(err_msg)
        httpx.post(f"{BROKER_URL}/command/result", json={
            "command_id": command_id,
            "result": err_msg
        }, timeout=10.0)
        return False
    finally:
        ssh.close()

def register_worker_key():
    """Read local public key and send it to the broker."""
    # Ensure we have a key first
    pkey = get_worker_pkey()
    if not pkey:
        logger.error("Cannot register worker: No private key available.")
        return

    pub_key = f"{pkey.get_name()} {pkey.get_base64()}"
    logger.debug(f"Registering worker public key: {pub_key[:30]}...")
    if pub_key:
        try:
            resp = httpx.post(f"{BROKER_URL}/worker/register", json={"public_key": pub_key}, timeout=10.0)
            if resp.status_code == 200:
                logger.debug("Registered worker public key with broker.")
            else:
                logger.error(f"[-] Failed to register worker key: {resp.status_code}")
        except Exception as e:
            logger.error(f"[-] Error registering worker key: {e}")


def get_reachable_ip():
    """Find the IP address of this worker that can reach the broker."""
    try:
        # Create a dummy socket to see which interface routes to the broker
        from urllib.parse import urlparse
        parsed = urlparse(BROKER_URL)
        if parsed.hostname and parsed.hostname not in ["localhost", "127.0.0.1"]:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((parsed.hostname, parsed.port or 8005))
            ip = s.getsockname()[0]
            s.close()
            return ip
    except Exception:
        pass
    
    # Fallback: check hostname -I
    try:
        import subprocess # nosec
        res = subprocess.check_output(["hostname", "-I"]).decode().split()[0]
        return res
    except Exception:
        return "127.0.0.1"

def worker_loop():
    global BROKER_URL
    import socket
    BROKER_URL = get_effective_broker_url()
    
    # Detect our own IP to report where Ollama is
    my_ip = get_reachable_ip()
    my_ollama_url = OLLAMA_URL
    if "localhost" in OLLAMA_URL or "127.0.0.1" in OLLAMA_URL:
        # Replace localhost with our actual IP so broker can reach us
        from urllib.parse import urlparse
        parsed = urlparse(OLLAMA_URL)
        my_ollama_url = f"{parsed.scheme}://{my_ip}:{parsed.port or 11434}"

    logger.debug(f"Worker details: Broker={BROKER_URL}, Ollama={my_ollama_url}")
    
    register_worker_key()
    
    logger.info(f"[READY] Worker connected to {BROKER_URL}. Listening for prompts...")
    
    iteration = 0
    while True:
        try:
            # 0. Report available models to broker (every 10 iterations)
            if iteration % 10 == 0:
                ollama_models = get_ollama_models()
                if ollama_models:
                    logger.info(f"[STATUS] Reporting {len(ollama_models)} models to broker...")
                models_payload = [
                    {"id": m, "remote_url": my_ollama_url} 
                    for m in ollama_models
                ]
                try:
                    # Always POST, even if empty, so broker knows worker is alive
                    httpx.post(f"{BROKER_URL}/worker/models", json={"models": models_payload}, timeout=5.0)
                    if ollama_models:
                        logger.debug(f"Reported {len(ollama_models)} models to broker.")
                except Exception as e:
                    logger.warning(f"Failed to report models to broker: {e}")

            # 1. Get all registered clients
            resp = httpx.get(f"{BROKER_URL}/clients", timeout=10.0)
            if resp.status_code == 200:
                clients = resp.json().get("clients", [])
                if not clients:
                    logger.debug("No clients registered.")
                    time.sleep(5)
                    iteration += 1
                    continue
                
                for client in clients:
                    if client is None:
                        continue
                    client_ip = client["ip"]
                    
                    # 2. Check for pending commands
                    cmd_resp = httpx.get(f"{BROKER_URL}/command/pending/{client_ip}", timeout=10.0)
                    if cmd_resp.status_code == 200:
                        cmds_data = cmd_resp.json()
                        cmds = cmds_data.get("commands", [])
                        if cmds:
                            logger.debug(f"Found {len(cmds)} pending commands for {client_ip}")
                        for cmd in cmds:
                            execute_remote_command(client, cmd["id"], cmd["command"])
                    
                    # 3. Check for generation (Context Sync Loop)
                    process_generation_request(client)
            else:
                logger.error(f"Broker error: {resp.status_code}")
            
            iteration += 1
        except Exception as e:
            if "localhost" in BROKER_URL or "127.0.0.1" in BROKER_URL:
                logger.error(f"FATAL: Connection refused to {BROKER_URL}. If your Broker is on a different VM, you MUST set BROKER_URL to the Broker's IP.")
            
            import traceback
            logger.error(f"Worker Loop Error: {e}")
            logger.error(traceback.format_exc())
        
        time.sleep(5)

if __name__ == "__main__":
    worker_loop()
