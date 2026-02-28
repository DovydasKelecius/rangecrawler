#!/bin/bash
read -p "Enter Broker IP Address: " BROKER_IP
echo "[*] Installing RangeCrawler Client Agent..."

# 1. Prerequisites
sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv openssh-server

# 2. Setup Directory
mkdir -p ~/rangecrawler/src/agent
cp src/agent/headless_client.py ~/rangecrawler/src/agent/
cp requirements.txt ~/rangecrawler/

# 3. Setup Venv
cd ~/rangecrawler
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 4. Ensure SSH is running
sudo systemctl enable --now ssh

echo "[+] Client setup complete in ~/rangecrawler"
echo "[*] To register, run: ./venv/bin/python src/agent/headless_client.py --broker http://$BROKER_IP:8000"
