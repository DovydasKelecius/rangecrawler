#!/bin/bash
read -p "Enter Broker IP Address: " BROKER_IP
read -p "Enter Ollama URL (default http://localhost:11434): " OLLAMA_URL
OLLAMA_URL=${OLLAMA_URL:-http://localhost:11434}
echo "[*] Installing RangeCrawler Worker (connecting to $BROKER_IP, using Ollama at $OLLAMA_URL)..."

# 1. Prerequisites
sudo apt-get update && sudo apt-get install -y docker.io docker-compose

# 2. Setup Directory Structure
mkdir -p ~/rangecrawler/src/worker
cp Dockerfile ~/rangecrawler/
cp src/worker/* ~/rangecrawler/src/worker/

# 3. Setup SSH Keys if they don't exist
if [ ! -f ~/.ssh/id_rsa ]; then
    echo "[*] Generating SSH key for Worker..."
    ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N ""
fi

# 4. Create worker docker-compose
cat <<EOF > ~/rangecrawler/docker-compose.yml
services:
  worker:
    build: .
    command: ["python", "src/worker/main.py"]
    network_mode: host
    volumes:
      - ./src:/app/src
      - ~/.ssh:/root/.ssh:ro
    environment:
      - PYTHONPATH=/app
      - BROKER_URL=http://$BROKER_IP:8000
      - OLLAMA_URL=$OLLAMA_URL
EOF

echo "[+] Worker setup complete in ~/rangecrawler"
echo "[*] Run 'docker compose up -d worker' to start."
