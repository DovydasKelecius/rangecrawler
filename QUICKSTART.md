# RangeCrawler Quickstart Guide

This guide explains how to deploy and use RangeCrawler to orchestrate AI agents across remote VMs.

## Prerequisites

- **VM 1 (Broker):** Linux with Docker and Docker Compose.
- **VM 2 (Worker):** Linux with Docker, Docker Compose, and [Ollama](https://ollama.com/) installed.
- **VM 3 (Client):** Linux with Python 3.10+ and OpenSSH server.

---

## 1. Setup VM 1: The Broker (Registry)

The Broker is the central API gateway and client registry.

1. Clone the repository and configure:
   ```bash
   git clone https://github.com/your-repo/RangeCrawler.git && cd RangeCrawler
   cp config.example.yaml config.yaml
   ```
2. Start the Broker:
   ```bash
   docker compose --profile broker up -d
   ```
   *The broker will listen on port 8005 by default.*

---

## 2. Setup VM 2: The Worker (Orchestrator)

The Worker connects to clients via SSH and handles AI generation via Ollama.

1. Clone the repository:
   ```bash
   git clone https://github.com/your-repo/RangeCrawler.git && cd RangeCrawler
   ```
2. Start the Worker (pointing to VM 1's IP and your Ollama instance):
   ```bash
   export BROKER_URL=http://<BROKER_IP>:8005
   export OLLAMA_URL=http://<OLLAMA_IP>:11434
   docker compose --profile worker up -d
   ```

---

## 3. Setup VM 3: The Client (Target)

The Agent registers the VM with the Broker and authorizes the Worker's SSH key.

1. Clone the repository and install:
   ```bash
   git clone https://github.com/your-repo/RangeCrawler.git && cd RangeCrawler
   python3 -m venv venv
   ./venv/bin/pip install .
   ```
2. Register the Client:
   ```bash
   # Register as root to allow administrative tasks via the agent
   sudo ./venv/bin/rangecrawler agent --broker http://<BROKER_IP>:8005 --user root
   ```

---

## 4. Usage: Modern Client CLI

From **any machine** (including your local laptop) with `rangecrawler` installed and access to the Broker:

### Initial Setup
Tell your CLI where the broker is:
```bash
rangecrawler client --broker http://<BROKER_IP>:8005 status
```

### List Resources
```bash
# See which models are available via the Worker
python3 src.main client models

# See which clients are registered
python3 src.main client clients
```

### Run Commands
Execute ad-hoc shell commands on a remote client:
```bash
python3 src.main client run "df -h" --ip <CLIENT_IP>
```

### Interactive AI Chat
Start a session where the LLM "inhabits" the remote VM. It can read files, run bash, and see directory structures.
```bash
rangecrawler client chat --ip <CLIENT_IP> --model llama3:latest
```
*In chat mode, the Worker handles all security and tool execution via the established SSH tunnel.*

---

## Monitoring & Troubleshooting

- **Broker Health:** `curl http://<BROKER_IP>:8005/health`
- **Check Registry:** `curl http://<BROKER_IP>:8005/clients`
- **View Logs:** `docker compose logs -f` (On VM 1 or VM 2)
- **Local State:** Chat history is saved on the client VM in `context.json`.
