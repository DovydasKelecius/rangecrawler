# RangeCrawler Usage Tutorial

## 1. Introduction
This tutorial covers the operational workflow for using RangeCrawler in a distributed environment.

## 2. Deploying the Agent
The fastest way to deploy an agent on a remote VM is using the one-liner provided by the Broker:

```bash
curl -sSL http://<BROKER_IP>:8005/install | bash -s -- http://<BROKER_IP>:8005
```

This command:
- Sets up a virtual environment in `~/.rangecrawler/`.
- Downloads the `headless_client.py` script.
- Installs a `systemd` service for background execution.
- Configures an `rc-agent` alias for easy management.

## 3. Whitelisting the Agent
By default, the Broker registers new agents but does not permit them to establish tunnels. An administrator must whitelist the agent:

```bash
python3 -m src.main admin permit <AGENT_UUID>
```

To find the Agent UUID, run `rc-agent --status` on the target machine or `python3 -m src.main admin agents` on the Broker.

## 4. Automatic Tunneling
Once an agent is permitted, the **Worker** will automatically establish a reverse SSH tunnel. This tunnel:
- Maps the Agent's local port `11434` to the Worker's **Shield Proxy**.
- Allows the Agent to perform inference using models hosted on the Worker.
- Restricts access to sensitive administrative endpoints (like model pulling or deletion).

## 5. Verifying Connectivity
On the Agent machine, you can verify the tunnel status:

```bash
# Check if the tunnel is active
rc-agent --status

# Test inference through the tunnel
curl http://localhost:11434/api/generate -d '{
  "model": "phi3",
  "prompt": "Hello!",
  "stream": false
}'
```

## 6. Troubleshooting
- **AttributeError: check_status**: Ensure you have the latest `headless_client.py` by re-running the installer.
- **Tunnel Not Open**: Check if the agent is permitted (`rc-agent --status` should show `PERMITTED: YES` in the admin view).
- **Ollama Signal Killed**: Usually indicates the Worker machine is out of memory (OOM). Check `docker logs` or `dmesg` on the Worker.
- **403 Forbidden**: You are attempting to access a blocked endpoint (e.g., trying to `pull` a model from an Agent). Only inference endpoints are whitelisted.
