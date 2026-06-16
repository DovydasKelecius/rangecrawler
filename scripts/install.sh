#!/bin/bash

# RangeCrawler Agent - One-line Installer
# Usage: curl -sSL https://raw.githubusercontent.com/DovydasKelecius/rangecrawler/main/scripts/install.sh | bash -s -- http://your-broker:8005

BROKER_URL=${1}

if [ -z "$BROKER_URL" ]; then
    read -p "Enter Broker URL (e.g., http://localhost:8005): " BROKER_URL
fi

echo "[*] Installing RangeCrawler Agent..."

# 0. Cleanup existing service to prevent overlap
if systemctl is-active --quiet rangecrawler-agent; then
    echo "[*] Stopping existing rangecrawler-agent..."
    sudo systemctl stop rangecrawler-agent
fi
if [ -f "/etc/systemd/system/rangecrawler-agent.service" ]; then
    sudo systemctl disable rangecrawler-agent
    sudo rm "/etc/systemd/system/rangecrawler-agent.service"
fi
sudo systemctl daemon-reload

# 1. Dependencies
if ! command -v python3 &> /dev/null; then
    echo "[-] Error: python3 not found."
    exit 1
fi

# 2. Setup Agent Directory and Venv
AGENT_DIR="$HOME/.rangecrawler"
mkdir -p "$AGENT_DIR"
AGENT_FILE="$AGENT_DIR/headless_client.py"
VENV_DIR="$AGENT_DIR/venv"

echo "[*] Setting up virtual environment..."
if ! python3 -m venv "$VENV_DIR"; then
    echo "[-] Error: Failed to create virtual environment. Please install python3-venv."
    exit 1
fi

# 3. Download Headless Client
echo "[*] Downloading agent script..."
curl -sSL "https://raw.githubusercontent.com/DovydasKelecius/rangecrawler/main/src/agent/headless_client.py" -o "$AGENT_FILE"

# 4. Install dependencies in Venv
echo "[*] Installing dependencies in virtual environment..."
if ! "$VENV_DIR/bin/pip" install httpx python-dotenv; then
    echo "[-] Error: Failed to install dependencies."
    exit 1
fi

# 5. Registration and Service Setup
echo "[*] Registering with Broker at $BROKER_URL..."
if ! "$VENV_DIR/bin/python3" "$AGENT_FILE" --broker "$BROKER_URL"; then
    echo "[-] Error: Registration failed."
    exit 1
fi

# 6. Optional Systemd Service
echo "[*] Setting up systemd service..."
cat <<EOF | sudo tee /etc/systemd/system/rangecrawler-agent.service > /dev/null
[Unit]
Description=RangeCrawler Autonomous Agent
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$AGENT_DIR
ExecStart=$VENV_DIR/bin/python3 $AGENT_FILE --broker $BROKER_URL --heartbeat
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable rangecrawler-agent

# 7. Add easy CLI alias
sed -i '/alias rc-agent/d' "$HOME/.bashrc"
echo "alias rc-agent='$VENV_DIR/bin/python3 $AGENT_FILE --broker $BROKER_URL'" >> "$HOME/.bashrc"

echo "[+] Agent installed and registered successfully."
echo "[*] Management commands:"
echo "    sudo systemctl start rangecrawler-agent   # Start background agent"
echo "    sudo systemctl status rangecrawler-agent  # Check if running"
echo "    rc-agent --status                        # Check tunnel status"
echo "    rc-agent --models                        # List available models"
echo "    rc-agent --uninstall                     # Remove agent completely"
