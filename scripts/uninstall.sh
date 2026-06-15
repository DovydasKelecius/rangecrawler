#!/bin/bash

# RangeCrawler Agent - Uninstaller
# Usage: curl -sSL https://raw.githubusercontent.com/DovydasKelecius/rangecrawler/main/scripts/uninstall.sh | bash

echo "[*] Uninstalling RangeCrawler Agent..."

AGENT_DIR="$HOME/.rangecrawler"
UUID_FILE="$HOME/.rc_agent_id"

if [ -d "$AGENT_DIR" ]; then
    rm -rf "$AGENT_DIR"
    echo "[+] Removed agent scripts."
fi

if [ -f "$UUID_FILE" ]; then
    rm "$UUID_FILE"
    echo "[+] Removed Agent UUID."
fi

echo "[!] Note: Check ~/.ssh/authorized_keys to manually remove any remaining session keys."
echo "[+] Uninstallation complete."
