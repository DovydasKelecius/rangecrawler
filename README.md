# RangeCrawler: Secure LLM Brokerage and Agent Orchestration

## 1. Overview

RangeCrawler is a distributed, secure brokerage system designed for the orchestration of Large Language Models (LLMs) and autonomous agent execution. It provides a centralized framework for managing model inference (via Ollama) and facilitating remote task execution in isolated workspaces through secure SSH tunneling. The system is engineered to ensure controlled access, resource auditing, and seamless integration between distributed compute nodes and client environments.

## 2. Core Architectural Components

The system architecture follows a modular design, comprising four primary entities:

- **Broker**: The central registry and permission arbiter (FastAPI). It manages model availability, client permissions, and secure communication tunnels.
- **Worker**: The execution engine integrated with Ollama. It processes inference requests and performs remote command execution on registered Agents.
- **Agent**: A lightweight client deployed on target machines to provide secure, isolated execution environments for remote tasks.
- **Client CLI**: A robust command-line interface for system administration, chat-based interaction, and resource provisioning.

## 3. Technology Stack

- **Backend**: Python 3.10+, FastAPI, Uvicorn
- **CLI**: Typer
- **Database**: SQLite
- **Communication**: SSH (Paramiko, SSHTunnel), HTTPX
- **Inference**: Ollama
- **Containerization**: Docker, Docker Compose

## 4. Quick Start Guide

### 4.1. Prerequisites

Ensure you have Python 3.10+ and a functional SSH server. For Worker nodes, an active Ollama instance is required.

### 4.2. Installation

```bash
git clone https://github.com/DovydasKelecius/rangecrawler.git
cd RangeCrawler
pip install -r requirements.txt
cp config.example.yaml config.yaml
cp .env.example .env
```

### 4.3. Deployment via Docker

The easiest way to initialize the core infrastructure is via Docker Compose:

```bash
docker compose up -d --build broker worker
```

### 4.4. Component Initialization

1.  **Start the Broker**: `python3 src/main.py broker`
2.  **Register an Agent**: `python3 src/main.py agent --broker http://<BROKER_IP>:8005`
3.  **Start the Worker**: `python3 src/main.py worker --broker-url http://<BROKER_IP>:8005`

## 5. Documentation

Detailed documentation is available in the `docs/` directory:

- [System Deployment and Configuration Guide](docs/setup-guide.md): Comprehensive instructions for installation and environment setup.
- [Operational Tutorial and User Manual](docs/usage-tutorial.md): Detailed guides for both administrators and clients.

## 6. License

This project is licensed under the MIT License.
