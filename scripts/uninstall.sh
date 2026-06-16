#!/bin/bash

# RangeCrawler Agent - Uninstaller
# Usage: curl -sSL https://raw.githubusercontent.com/DovydasKelecius/rangecrawler/main/scripts/uninstall.sh | bash

echo "[*] Uninstalling RangeCrawler Agent..."

AGENT_DIR="$HOME/.rangecrawler"
UUID_FILE="$HOME/.rc_agent_id"

# 1. Stop and remove systemd service
if systemctl is-active --quiet rangecrawler-agent; then
    echo "[*] Stopping rangecrawler-agent service..."
    sudo systemctl stop rangecrawler-agent
fi

if [ -f "/etc/systemd/system/rangecrawler-agent.service" ]; then
    echo "[*] Removing systemd service..."
    sudo systemctl disable rangecrawler-agent
    sudo rm /etc/systemd/system/rangecrawler-agent.service
    sudo systemctl daemon-reload
fi

# 2. Remove files
if [ -d "$AGENT_DIR" ]; then
    rm -rf "$AGENT_DIR"
    echo "[+] Removed agent scripts."
fi

if [ -f "$UUID_FILE" ]; then
    rm "$UUID_FILE"
    echo "[+] Removed Agent UUID."
fi

# 3. Remove alias
if grep -q "alias rc-agent" "$HOME/.bashrc"; then
    echo "[*] Removing rc-agent alias..."
    sed -i '/alias rc-agent/d' "$HOME/.bashrc"
fi

echo "[!] Note: Check ~/.ssh/authorized_keys to manually remove any remaining session keys."
echo "[+] Uninstallation complete. Please restart your shell or run 'source ~/.bashrc'."
