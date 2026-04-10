# RangeCrawler: System Deployment and Configuration Guide

## 1. Introduction
This document provides a comprehensive technical guide for the deployment and configuration of RangeCrawler, a distributed brokerage system designed for secure Large Language Model (LLM) orchestration and remote agent execution. The architecture comprises four primary entities: the **Broker**, the **Worker**, the **Agent**, and the **Client CLI**.

## 2. System Architecture Overview
The RangeCrawler framework operates on a hub-and-spoke model where the Broker serves as the central registry and permission arbiter. 
- **Broker**: A FastAPI-based central server managing model registries, client permissions, and secure communication tunnels.
- **Worker**: An execution node integrated with the Ollama inference engine, responsible for performing remote tasks via SSH.
- **Agent**: A lightweight client deployed on target workspaces to provide secure, isolated execution environments.
- **Client CLI**: The administrative and user interface for system interaction.

## 3. Prerequisites
Successful deployment requires the following environment specifications:
- **Operating System**: Linux (recommended) or macOS.
- **Runtime**: Python 3.10 or higher.
- **Containerization**: Docker and Docker Compose (optional, for containerized deployment).
- **Inference Engine**: Ollama (required for Worker nodes).
- **Dependencies**: SSH server (sshd) must be active on Agent nodes.

## 4. Installation Procedures

### 4.1. Local Environment Setup
To initialize the Python environment and install necessary dependencies, execute the following commands:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4.2. Configuration Initialization
The system utilizes a hierarchical configuration approach via `config.yaml` and environment-specific variables in a `.env` file.
```bash
cp config.example.yaml config.yaml
cp .env.example .env
```
*Note: Ensure the `BROKER_URL` in the `.env` file correctly points to the Broker's accessible IP address.*

## 5. Deployment via Docker
For containerized orchestration, RangeCrawler utilizes Docker Compose. This method ensures environment parity and simplifies network management.

### 5.1. Building and Starting Services
```bash
docker compose up -d --build broker worker
```

### 5.3. Networking Considerations
When deploying via Docker Compose, the **Worker** utilizes `network_mode: host` to facilitate communication with a local Ollama instance on the host machine. Consequently, the `BROKER_URL` in the `.env` file should typically be set to `http://localhost:8005` if the Broker is mapping its port to the host. If the components are distributed across different physical machines, this URL must point to the Broker's external IP address.

## 6. Component-Specific Execution

### 6.1. Starting the Broker
The Broker must be the first component initialized to facilitate subsequent registrations.
```bash
python3 src/main.py broker --host 0.0.0.0 --port 8005
```

### 6.2. Deploying the Agent
On the target machine providing the workspace, run the Agent to register with the Broker:
```bash
python3 src/main.py agent --broker http://<BROKER_IP>:8005
```

### 6.3. Initializing the Worker
The Worker connects to both the Broker and a local Ollama instance:
```bash
python3 src/main.py worker --broker-url http://<BROKER_IP>:8005 --ollama-url http://localhost:11434
```

## 7. Administrative Management
Access control is managed through the administrative sub-command. To grant a client access to a specific model with a usage quota:
```bash
python3 src/main.py admin grant <CLIENT_IP> <MODEL_ID> --quota 3600
```