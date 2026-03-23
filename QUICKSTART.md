# RangeCrawler Quickstart Guide

RangeCrawler is a distributed system for orchestrating AI agents across remote VMs.

## Prerequisites
- **Broker VM:** Registry and API Gateway (Port 8000).
- **Worker VM:** Orchestrates agents and handles LLM inference (Ollama).
- **Client VM:** The target machine where the agent will perform tasks.

---

## 1. Broker Setup (VM 1)
1. Clone and Configure:
   ```bash
   git clone https://github.com/your-repo/RangeCrawler.git && cd RangeCrawler
   cp config.example.yaml config.yaml
   ```
2. Start Broker:
   ```bash
   python src/main.py broker
   ```

---

## 2. Worker Setup (VM 2)
1. Install Dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start Worker:
   ```bash
   export BROKER_URL=http://<BROKER_IP>:8000
   export OLLAMA_URL=http://localhost:11434
   python src/main.py worker
   ```

---

## 3. Client Agent Setup (VM 3)
1. Register the VM:
   ```bash
   python src/main.py agent --broker http://<BROKER_IP>:8000 --user root
   ```

---

## 4. Usage (Admin & Client)

### Admin: Grant Access
On the Broker machine:
```bash
python src/main.py admin grant <CLIENT_IP> <MODEL_ID>
```

### Client: Status & Chat
On any machine with the CLI:
```bash
# Check connectivity and permitted models
python src/main.py client --broker http://<BROKER_IP>:8000 status

# Start interactive agent chat
python src/main.py client chat --model <MODEL_ID>
```

---

## Troubleshooting
- **Check IP:** Run `python src/main.py agent` on the client to see what IP it uses.
- **Broker Health:** `curl http://<BROKER_IP>:8000/health`
- **Logs:** Check console output for debug information.
