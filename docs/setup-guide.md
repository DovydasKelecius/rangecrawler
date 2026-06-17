# RangeCrawler: System Deployment and Configuration Guide

## 1. Overview
This guide details the deployment of the RangeCrawler ecosystem, focusing on the automated Agent lifecycle and central Broker administration.

## 2. Agent Deployment (Client Side)

The RangeCrawler Agent is designed for "zero-config" deployment on client machines (VMs or physical hardware).

### 2.1. Automated Installation
Execute the following one-liner on the client machine to install the Agent as a background service:

```bash
curl -sSL http://<BROKER_IP>:8005/install | bash -s -- http://<BROKER_IP>:8005
```

**What this script does:**
1. Generates a persistent, hardware-bound UUID in `~/.rc_agent_id`.
2. Creates a virtual environment in `~/.rangecrawler/venv`.
3. Registers the Agent identity with the central Broker.
4. Installs a `systemd` service for autonomous heartbeats and polling.
5. Adds the `rc-agent` alias for manual management.

### 2.2. Command-Line Interface (`rc-agent`)

| Argument | Description |
| :--- | :--- |
| `--status` | Displays the current connection status and hardware UUID. |
| `--models` | Lists the AI models authorized for this agent by the administrator. |
| `--broker <URL>` | Overrides the default Broker URL. |
| `--heartbeat` | Triggers a manual registration/heartbeat poll. |
| `--uninstall` | Triggers the uninstallation script. |

### 2.3. Uninstallation
To remove all Agent components, services, and identity data:

```bash
rc-agent --uninstall
# OR
curl -sSL http://<BROKER_IP>:8005/uninstall | bash
```

## 3. Infrastructure Setup (Server Side)

### 3.1. Starting the Broker
The Broker serves the API and the automated installation scripts.

```bash
# Start via alias (if setup_services.sh was run)
rc-broker
# OR via module
python3 -m src.main broker
```

### 3.2. Administrative CLI (`rc-admin`)
The `rc-admin` command (alias for `src/main.py admin`) manages the trust registry.

- **Permit an Agent**: `rc-admin permit <UUID>`
- **Grant Model**: `rc-admin grant <UUID> <MODEL_NAME> --quota <SECONDS>`
- **List Agents**: `rc-admin list`
- **Revoke Access**: `rc-admin revoke <UUID> <MODEL_NAME>`

## 4. Worker Initialization
Workers must be connected to a GPU-enabled Ollama instance.

```bash
# Start via alias
rc-worker
# OR via manual parameters
python3 -m src.main worker --broker-url http://<BROKER_IP>:8005 --ollama-url http://localhost:11434
```
