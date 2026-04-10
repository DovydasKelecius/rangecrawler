# RangeCrawler: Operational Tutorial and User Manual

## 1. Introduction

This tutorial provides a systematic methodology for interacting with the RangeCrawler ecosystem. It is divided into two primary sections: the **Administrator's Perspective**, focusing on system governance, resource allocation, and monitoring; and the **Client's Perspective**, focusing on model interaction, task execution, and resource provisioning.

---

## 2. Administrator's Perspective: System Governance

The Administrator is responsible for the integrity of the brokerage system, ensuring that computational resources (LLMs) are correctly registered and that client access is governed by strict security policies.

### 2.1. Model Registry Management

Before any client interaction can occur, models must be registered within the Broker's database. Models are typically added via the `config.yaml` file during initialization, but their status can be audited via the CLI:

```bash
python3 src/main.py admin models
```

This command provides a listing of all active models and their associated remote inference URLs (typically pointing to Worker nodes).

### 2.2. Client Permission Arbitration

RangeCrawler operates on a "Zero Trust" principle by default. Access to any model must be explicitly granted to a client's IP address.

**Procedure for Granting Access:**
To authorize a client (IP: `192.168.1.50`) to utilize the `llama3` model with a total usage quota of one hour (3600 seconds), execute:

```bash
python3 src/main.py admin grant 192.168.1.50 llama3 --quota 3600 --tools
```

The `--tools` flag indicates that the client is permitted to execute tool-based tasks (e.g., remote shell commands) via the LLM.

### 2.3. Usage Auditing and Monitoring

Administrators can monitor the real-time usage and remaining quotas of all registered clients:

```bash
python3 src/main.py admin permissions
```

This report facilitates the identification of resource exhaustion and ensures compliance with allocated computational budgets.

---

## 3. Client's Perspective: Resource Interaction

The Client interacts with the Broker to perform inference tasks, execute remote operations, and manage their local agent workspace.

### 3.1. Workspace Registration via Agent

A client must first establish a secure workspace by running the RangeCrawler Agent. This enables the system to perform remote operations on the client's behalf:

```bash
python3 src/main.py agent --broker http://<BROKER_IP>:8005
```

Once registered, the Broker identifies the client's IP and prepares the secure SSH tunnel for the Worker.

### 3.2. Synchronous Interaction (Chat Mode)

Clients can engage in a stateful dialogue with an authorized model using the `chat` sub-command:

```bash
python3 src/main.py client chat --model llama3
```

This interface supports continuous context management, allowing for complex multi-turn reasoning within the terminal.

### 3.3. Resource Provisioning

For tasks requiring isolated computational resources or specific model configurations, clients can request a provisioned instance:

```bash
python3 src/main.py client provision llama3 --timeout 60
```

This command signals the Worker to prepare a dedicated environment for the requested model, ensuring high availability and isolation.

### 3.4. Remote Task Execution

Clients can dispatch arbitrary shell commands to be executed within their registered workspace via the Broker:

```bash
python3 src/main.py client run "ls -la /app/data" --ip <AGENT_IP>
```

The system handles the command queuing, remote execution through the secure tunnel, and returns the output to the client's terminal.

---

## 4. Conclusion

By adhering to these operational protocols, Administrators can ensure a secure and efficient brokerage environment, while Clients can leverage the full power of distributed LLMs and remote agent orchestration. This systematic approach to usage maintains the integrity and scalability of the RangeCrawler framework.
