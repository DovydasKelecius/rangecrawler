#!/bin/bash
echo "[*] Installing RangeCrawler Broker..."

# 1. Prerequisites
sudo apt-get update && sudo apt-get install -y docker.io docker-compose sqlite3

# 2. Setup Directory Structure
mkdir -p ~/rangecrawler/src/broker
cp Dockerfile ~/rangecrawler/
cp config.example.yaml ~/rangecrawler/config.yaml
cp src/broker/* ~/rangecrawler/src/broker/
cp src/main.py ~/rangecrawler/src/

# 3. Create initial DB
touch ~/rangecrawler/rangecrawler.db
chmod 666 ~/rangecrawler/rangecrawler.db

# 4. Create minimal docker-compose
cat <<EOF > ~/rangecrawler/docker-compose.yml
services:
  broker:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./config.yaml:/app/config.yaml
      - ./src:/app/src
      - ./rangecrawler.db:/app/rangecrawler.db
    environment:
      - PYTHONPATH=/app
EOF

echo "[+] Broker setup complete in ~/rangecrawler"
echo "[*] Run 'docker compose up -d broker' to start."
