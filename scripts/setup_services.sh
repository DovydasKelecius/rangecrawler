#!/bin/bash

# RangeCrawler Infrastructure Setup - Broker & Worker systemd services
# Usage: ./scripts/setup_services.sh

REPO_DIR=$(pwd)
VENV_DIR="$REPO_DIR/venv"
USER=$(whoami)

if [ ! -d "$VENV_DIR" ]; then
    echo "[-] Error: Virtual environment not found at $VENV_DIR. Please run setup first."
    exit 1
fi

echo "[*] Setting up RangeCrawler Infrastructure Services..."

# 1. Broker Service
echo "[*] Creating rangecrawler-broker.service..."
cat <<EOF | sudo tee /etc/systemd/system/rangecrawler-broker.service > /dev/null
[Unit]
Description=RangeCrawler Broker
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$REPO_DIR
Environment="RANGECRAWLER_CONFIG=$REPO_DIR/config.yaml"
ExecStart=$VENV_DIR/bin/python3 src/main.py broker
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 2. Worker Service
echo "[*] Creating rangecrawler-worker.service..."
# Note: Uses environment variables from .env if present, or defaults
cat <<EOF | sudo tee /etc/systemd/system/rangecrawler-worker.service > /dev/null
[Unit]
Description=RangeCrawler Worker
After=network.target rangecrawler-broker.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$REPO_DIR
# Load environment variables from .env for BROKER_URL and OLLAMA_URL
EnvironmentFile=-$REPO_DIR/.env
ExecStart=$VENV_DIR/bin/python3 src/main.py worker
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload

# 3. Add easy CLI aliases
echo "[*] Adding aliases to .bashrc..."
echo "alias rc-broker='$VENV_DIR/bin/python3 $REPO_DIR/src/main.py broker'" >> "$HOME/.bashrc"
echo "alias rc-worker='$VENV_DIR/bin/python3 $REPO_DIR/src/main.py worker'" >> "$HOME/.bashrc"

echo "[+] Services created and aliases added successfully."
echo "[*] Management commands:"
echo "    Broker: sudo systemctl status rangecrawler-broker"
echo "    Worker: sudo systemctl status rangecrawler-worker"
echo "    Manual: rc-broker --help | rc-worker --help"
echo ""
echo "[*] View logs:"
echo "    journalctl -u rangecrawler-broker -f"
echo "    journalctl -u rangecrawler-worker -f"
