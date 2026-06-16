#!/bin/bash

# RangeCrawler Infrastructure Setup - Modular Service Installer
# Usage: ./scripts/setup_services.sh [broker|worker]

COMPONENT=$1
REPO_DIR=$(pwd)
VENV_DIR="$REPO_DIR/venv"
USER=$(whoami)

if [[ "$COMPONENT" != "broker" && "$COMPONENT" != "worker" ]]; then
    echo "[-] Usage: ./scripts/setup_services.sh [broker|worker]"
    exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "[-] Error: Virtual environment not found at $VENV_DIR. Please run setup first."
    exit 1
fi

echo "[*] Setting up RangeCrawler $COMPONENT Service..."

# 0. Cleanup existing services to prevent overlap
echo "[*] Cleaning up existing RangeCrawler services..."
for svc in rangecrawler-broker rangecrawler-worker rangecrawler-agent; do
    if systemctl is-active --quiet $svc; then
        sudo systemctl stop $svc
    fi
    if [ -f "/etc/systemd/system/$svc.service" ]; then
        sudo systemctl disable $svc
        sudo rm "/etc/systemd/system/$svc.service"
    fi
done
sudo systemctl daemon-reload

if [[ "$COMPONENT" == "broker" ]]; then
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
Environment="PYTHONPATH=$REPO_DIR"
ExecStart=$VENV_DIR/bin/python3 -m src.main broker
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable --now rangecrawler-broker
    
    # Alias
    sed -i '/alias rc-broker/d' "$HOME/.bashrc"
    echo "alias rc-broker='cd $REPO_DIR && PYTHONPATH=$REPO_DIR $VENV_DIR/bin/python3 -m src.main broker'" >> "$HOME/.bashrc"
    echo "[+] Broker service and 'rc-broker' alias ready."

elif [[ "$COMPONENT" == "worker" ]]; then
    # 2. Worker Service
    # Check for .env or prompt
    if [ ! -f "$REPO_DIR/.env" ]; then
        read -p "Enter Broker URL (e.g., http://10.1.0.129:8005): " BROKER_URL
        read -p "Enter Ollama URL (e.g., http://localhost:11434): " OLLAMA_URL
        echo "BROKER_URL=$BROKER_URL" > "$REPO_DIR/.env"
        echo "OLLAMA_URL=$OLLAMA_URL" >> "$REPO_DIR/.env"
    fi

    echo "[*] Creating rangecrawler-worker.service..."
    cat <<EOF | sudo tee /etc/systemd/system/rangecrawler-worker.service > /dev/null
[Unit]
Description=RangeCrawler Worker
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$REPO_DIR
EnvironmentFile=$REPO_DIR/.env
Environment="PYTHONPATH=$REPO_DIR"
ExecStart=$VENV_DIR/bin/python3 -m src.main worker
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable --now rangecrawler-worker
    
    # Alias
    sed -i '/alias rc-worker/d' "$HOME/.bashrc"
    echo "alias rc-worker='cd $REPO_DIR && PYTHONPATH=$REPO_DIR $VENV_DIR/bin/python3 -m src.main worker'" >> "$HOME/.bashrc"
    echo "[+] Worker service and 'rc-worker' alias ready."
fi

echo "[*] To apply aliases immediately, run: source ~/.bashrc"
