# RangeCrawler Deployment Guide

This guide explains how to install and orchestrate RangeCrawler across 3 separate VMs.

## Prerequisites

- **VM 1 (Broker):** Linux with Docker and Docker Compose installed.
- **VM 2 (Worker):** Linux with Docker and Docker Compose. SSH keys in `~/.ssh`.
- **VM 3 (Client):** Linux with Python 3.10+ and OpenSSH server.

---

## 1. Setup VM 1: The Broker

The Broker is the central registry and API gateway.

1. Clone the repository:
   ```bash
   git clone https://github.com/your-repo/RangeCrawler.git && cd RangeCrawler
   ```
2. Configure (optional):
   ```bash
   cp config.example.yaml config.yaml
   ```
3. Start the Broker:
   ```bash
   docker compose --profile broker up -d
   ```

---

## 2. Setup VM 2: The Worker

The Worker polls the broker and initiates secure SSH connections to clients.

1. Clone the repository:
   ```bash
   git clone https://github.com/your-repo/RangeCrawler.git && cd RangeCrawler
   ```
2. Start the Worker (replace `<BROKER_IP>` with VM 1's IP):
   ```bash
   export BROKER_URL=http://<BROKER_IP>:8000
   export OLLAMA_URL=http://localhost:11434  # URL where Ollama is running
   docker compose --profile worker up -d
   ```

---

## 3. Setup VM 3: The Client (Agent)

The Agent registers the machine and authorizes the worker.

1. Clone the repository:
   ```bash
   git clone https://github.com/your-repo/RangeCrawler.git && cd RangeCrawler
   ```
2. Setup environment:
   ```bash
   python3 -m venv venv
   ./venv/bin/pip install .
   ```
3. Register the Client (replace `<BROKER_IP>` with VM 1's IP):
   ```bash
   # Register as root to allow administrative tasks (ad-hoc commands)
   sudo ./venv/bin/python -m src.main agent --broker http://<BROKER_IP>:8000 --user root
   ```

---

## 4. Usage: Running Ad-Hoc Commands

From **any machine** with the repository and access to the Broker:

```bash
# Example: Remove a package from VM 3 (The Client)
./venv/bin/python submit_command.py "pacman -Rs --noconfirm cmatrix" --ip <CLIENT_IP> --wait
```

_Note: `<CLIENT_IP>` is the IP the agent reported during registration (usually the Docker gateway or the VM's public IP)._

---

## 5. Usage: AI Interaction

To chat with the VM environment:

1. **On VM 3 (Client):**
   ```bash
   echo "Hello AI, what is my disk usage?" > prompt.txt
   ```
2. **What happens:**
   - The **Worker (VM 2)** detects the prompt.
   - It connects to **Client (VM 3)** via SSH.
   - It queries **Ollama** and executes tools if necessary.
   - It writes the answer to `context.json` on **VM 3** and deletes `prompt.txt`.

---

## Monitoring

- **Check Registry:** `curl http://<BROKER_IP>:8000/clients`
- **Check Logs:** `docker compose logs -f` (On VM 1 or VM 2)
- **Check History:** `cat context.json` (On VM 3)
