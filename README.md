# RangeCrawler: Secure LLM Brokerage & Agent Orchestration

RangeCrawler is a secure, distributed brokerage system designed for on-demand AI service delivery. It solves the "GPU-in-Virtualization" bottleneck by decoupling high-performance compute nodes (Workers) from restricted execution environments (Agents) via a **Zero-Trust Triple Handshake** and encrypted **Reverse SSH Tunneling**.

---

## Infrastructure Setup (Broker & Worker)

The main RangeCrawler infrastructure requires a Python 3.10+ environment. Follow these steps to set up the Broker and Worker nodes.

### 1. Clone & Environment Preparation
```bash
git clone https://github.com/DovydasKelecius/rangecrawler.git
cd rangecrawler

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Deploy Services
Use the provided modular setup script to install the systemd services and CLI aliases.

#### Setup Broker
Run this on your control plane server:
```bash
./scripts/setup_services.sh broker
source ~/.bashrc
```

#### Setup Worker
Run this on your GPU-equipped compute node:
```bash
./scripts/setup_services.sh worker
source ~/.bashrc
```
*Note: The worker setup will prompt for the Broker URL and Ollama URL if no `.env` file exists.*

---

## Quick Start (Client Machine)

Deploy a lightweight, hardware-bound agent on any remote machine with a single command:

```bash
# Automated Installation
curl -sSL http://<BROKER_IP>:8005/install | bash -s -- http://<BROKER_IP>:8005

# Verify Installation
rc-agent --status
```

---

## System Architecture

The system operates across three specialized planes:

1.  **Broker (Control Plane)**: Central arbiter for identity and ACL. Manages JIT credentialing.
2.  **Worker (Compute Plane)**: GPU-equipped host running Ollama and the **Shield Proxy** (Inference Firewall).
3.  **Agent (Client Space)**: Lightweight endpoint providing a local loopback (`localhost:11434`) to remote GPUs.

---

## Service Management (systemd)

All RangeCrawler components are managed as standard `systemd` services for high availability and autonomous recovery.

### Component Services
| Entity | Service Name | Description |
| :--- | :--- | :--- |
| **Broker** | `rangecrawler-broker` | API & Registration Hub |
| **Worker** | `rangecrawler-worker` | Compute & Tunnel Engine |
| **Agent** | `rangecrawler-agent` | Loopback & Key Management |

### Management Commands
| Action | Command |
| :--- | :--- |
| **Start Service** | `sudo systemctl start <service-name>` |
| **Stop Service** | `sudo systemctl stop <service-name>` |
| **Restart Service** | `sudo systemctl restart <service-name>` |
| **View Live Logs** | `journalctl -u <service-name> -f` |
| **Check Status** | `systemctl status <service-name>` |

---

## Command Line Interface (CLI)

### Agent CLI (`rc-agent`)
| Argument | Description |
| :--- | :--- |
| `--status` | Show connection status and hardware UUID. |
| `--models` | List AI models authorized for this agent. |
| `--heartbeat` | Manually trigger identity registration poll. |
| `--uninstall` | Completely remove agent and service from machine. |

### Admin CLI (`rc-admin`)
Used on the Broker machine to manage the trust registry.
```bash
# Permit a newly registered hardware UUID
rc-admin permit <AGENT_UUID>

# Grant model access (e.g., Llama3 with 1h quota)
rc-admin grant <AGENT_UUID> llama3 --quota 3600

# Revoke access
rc-admin revoke <AGENT_UUID> llama3
```

---

## Uninstallation

To remove all components, virtual environments, and service configurations from a client machine:

```bash
# One-liner via curl
curl -sSL http://<BROKER_IP>:8005/uninstall | bash

# OR via CLI alias
rc-agent --uninstall
```

---

## License
Distributed under the MIT License. See `LICENSE` for more information.
