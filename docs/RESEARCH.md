# RangeCrawler: Architecture for Secure LLM Orchestration

## 1. Research Significance
RangeCrawler provides a standardized, secure testbed for researching **Autonomous Agent Safety**, **Zero Trust LLM Orchestration**, and **Distributed Inference**. By isolating execution environments (Agents) from the inference providers (Workers) via reverse SSH tunneling and a Shield Proxy, the system allows for high-fidelity cyber-range experiments without compromising the security of the host infrastructure.

## 2. Formal Security Architecture

### 2.1. Zero Trust Triple Handshake
The system implements a four-stage ephemeral key exchange to eliminate static credential risks:
1.  **Handshake Init**: Worker generates ED25519 session keys and registers the public key with the Broker.
2.  **Handshake Poll**: Agent detects the pending request via an authenticated long-polling channel.
3.  **Key Authorization**: Agent injects the key into `~/.ssh/authorized_keys` with scope-based constraints (`restrict,port-forwarding`).
4.  **Verification**: Broker confirms authorization, allowing the Worker to establish the tunnel.

### 2.2. Shield Proxy (Inference Firewall)
Located on the Worker node, the Shield Proxy intercepts reverse-tunneled traffic to enforce a strict whitelist of API endpoints:
- **Permitted**: `/api/generate`, `/api/chat`, `/api/tags`.
- **Blocked**: `/api/pull`, `/api/delete`, `/api/create`.
This prevents compromised agents from modifying the model registry or exfiltrating model weights.

## 3. Modular Implementation Guide

### 3.1. Infrastructure Nodes (Broker/Worker)
For reproducible research environments, deploy infrastructure components as system-level services:
```bash
# Setup targeted component
./scripts/setup_services.sh [broker|worker]
source ~/.bashrc
```

### 3.2. Execution Nodes (Agents)
Agents are designed for lightweight deployment in VMs or containers:
```bash
curl -sSL http://<BROKER_IP>:8005/install | bash -s -- http://<BROKER_IP>:8005
```

## 4. Operational Commands (RC-Ecosystem)

| Entity | CLI Alias | Primary Research Task |
| :--- | :--- | :--- |
| **Broker** | `rc-broker` | Traffic monitoring and permission arbitration. |
| **Worker** | `rc-worker` | Inference orchestration and tunnel management. |
| **Agent** | `rc-agent` | Local execution monitoring (`--status`) and model listing (`--models`). |
| **Admin** | `main.py admin` | Whitelisting agents (`permit`) and granting model access (`grant`). |

## 5. Potential Research Applications
- **Malicious Prompt Injection**: Testing agent behavior when receiving adversarial inputs through the shielded tunnel.
- **Resource Exhaustion Attacks**: Analyzing Worker stability (OOM scenarios) under heavy inference load from multiple Agents.
- **Lateral Movement Prevention**: Auditing the effectiveness of SSH `restrict` constraints in preventing escape from the Agent workspace.
