#!/bin/bash

# RangeCrawler Agent - One-line Installer
# Usage: curl -sSL https://raw.githubusercontent.com/DovydasKelecius/rangecrawler/main/scripts/install.sh | bash -s -- http://your-broker:8005

BROKER_URL=${1}

if [ -z "$BROKER_URL" ]; then
    read -p "Enter Broker URL (e.g., http://localhost:8005): " BROKER_URL
fi

echo "[*] Installing RangeCrawler Agent..."

# 1. Dependencies
if ! command -v python3 &> /dev/null; then
    echo "[-] Error: python3 not found."
    exit 1
fi

# 2. Download Headless Client
AGENT_DIR="$HOME/.rangecrawler"
mkdir -p "$AGENT_DIR"
AGENT_FILE="$AGENT_DIR/headless_client.py"

echo "[*] Downloading agent script..."
# Use the repo path or broker redirect
curl -sSL "https://raw.githubusercontent.com/DovydasKelecius/rangecrawler/main/src/agent/headless_client.py" -o "$AGENT_FILE"

# 3. Pip dependencies
echo "[*] Ensuring Python dependencies..."
pip3 install httpx python-dotenv &> /dev/null

# 4. Registration
echo "[*] Registering with Broker at $BROKER_URL..."
python3 "$AGENT_FILE" --broker "$BROKER_URL"

echo "[+] Agent installed and registered successfully."
echo "[*] To keep agent running, use: python3 $AGENT_FILE --broker $BROKER_URL --heartbeat"
