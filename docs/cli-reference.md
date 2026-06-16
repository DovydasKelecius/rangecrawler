# RangeCrawler: Command-Line Interface (CLI) Reference Specification

## 1. Introduction
This reference manual provides a detailed technical specification of the RangeCrawler Command-Line Interface (CLI). The system utilizes a multi-tiered CLI architecture, now standardized across all nodes via convenient `rc-` aliases.

---

## 2. Server Infrastructure Aliases
These aliases are configured via `scripts/setup_services.sh` to manage backend components.

### 2.1. `rc-broker`
**Description**: Start or configure the Broker server.

**Syntax**: `rc-broker [OPTIONS]`

- **Options**:
  - `--host <HOST>`: Binding host.
  - `--port <PORT>`: Binding port.
  - `--reload`: Enable auto-reload for development.

### 2.2. `rc-worker`
**Description**: Start or configure the Worker inference orchestrator.

**Syntax**: `rc-worker [OPTIONS]`

- **Options**:
  - `--broker-url <URL>`: Broker connectivity URL.
  - `--ollama-url <URL>`: Ollama inference engine URL.

---

## 3. Administrative Interface (`admin`)
Accessed via `python3 src/main.py admin [COMMAND]` or `rc-broker admin [COMMAND]`.

### 3.1. `admin grant`
**Description**: Authorizes model access to a specific client.
**Syntax**: `grant <UUID> <MODEL_ID>`

### 3.2. `admin models`
**Description**: List all registered models in the Broker.

### 3.3. `admin permissions`
**Description**: List client model permissions.

### 3.4. `admin agents`
**Description**: List all registered agents and their permit status.

### 3.5. `admin permit`
**Description**: Whitelist or revoke an agent for automatic reverse tunneling.
**Syntax**: `permit <AGENT_UUID> [--permit/--no-permit]`

---

## 4. Agent Interface (`rc-agent`)
Accessed via `rc-agent` alias on registered VM nodes.

### 4.1. `rc-agent --status`
**Description**: Checks local tunnel health and session keys.

### 4.2. `rc-agent --models`
**Description**: Queries the Worker via tunnel to list available Ollama models.

### 4.3. `rc-agent --uninstall`
**Description**: Triggers automated cleanup of the Agent installation, including systemd service and aliases.

### 4.4. `rc-agent --heartbeat`
**Description**: Starts the agent in long-polling mode (usually managed by systemd).

---

## 5. Client Interface (`client`)
Accessed via `python3 src/main.py client [COMMAND]`.

### 5.1. `client status`
Displays client environment, Broker URL, and permitted models.

### 5.2. `client chat`
Initiates a stateful, interactive session.

### 5.3. `client provision`
Provisions a dedicated LLM instance.

---
*For direct interaction with the underlying application entry point, use `python3 src/main.py [COMMAND]`.*
