# RangeCrawler Remote Workspace Setup

This document describes how to automate the connection between a local PC (the Client) and the RangeCrawler Broker.

## 1. Broker Configuration

The broker must be running and accessible over the network.
Ensure `config.yaml` has the `gemini_api_key` set.

## 2. Autonomous Agent (Local PC)

The agent script `src/agent/headless_client.py` allows your local PC to "call home" to the broker and register itself as an SSH-accessible workspace.

### Commands

To register your current machine with the broker:

```bash
# Replace <BROKER_IP> with the actual IP of the broker server
python src/agent/headless_client.py --broker http://<BROKER_IP>:8000 --heartbeat
```

### Automation (Systemd)

To run this automatically on Linux startup, create `/etc/systemd/system/rangecrawler-agent.service`:

```ini
[Unit]
Description=RangeCrawler Autonomous Agent
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/kedo/RangeCrawler/src/agent/headless_client.py --broker http://<BROKER_IP>:8000 --heartbeat
Restart=always
User=kedo
WorkingDirectory=/home/kedo/RangeCrawler

[Install]
WantedBy=multi-user.target
```

## 3. SSH Requirements

For the Broker to actually execute commands on your PC:

1. Your PC must have `openssh-server` installed and running.
2. The Broker must have your PC's SSH public key (or you must provide the path to a private key in the registration/config).
