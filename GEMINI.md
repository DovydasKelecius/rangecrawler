# GEMINI.md - RangeCrawler

This document serves as the primary instructional context for AI agents working on the RangeCrawler project. It defines the decentralized, robust architecture for connecting LLM services to target environments.

## 1. Project Philosophy: The Decentralized Registry Pattern
RangeCrawler is shifting from a standard proxy model to a **Decentralized Registry & Worker** architecture. The goal is to provide LLM capabilities to remote "Client VMs" while maintaining robustness, state persistence on the edge, and scalability of the inference backend.

### The Three Pillars
1.  **The Client VM (The Subject):**
    *   The target environment being analyzed or simulated.
    *   **Context Ownership:** Holds the primary "Source of Truth" (conversation history and environment state) in a local `context.json`.
    *   **Access Point:** Provides an SSH interface for the Worker to connect and execute instructions.
2.  **The Broker (The Registry):**
    *   A lightweight, centralized FastAPI service running in a container.
    *   **Role:** Acts as a meeting point (mailbox). It stores metadata about clients (IP, SSH keys, UUIDs, requested models) in a SQLite database.
    *   **Passive Nature:** It does not execute tools. It merely holds the "Request Queue" for Workers to poll.
3.  **The Ollama Service / Worker (The Brain):**
    *   A separate VM or cluster running Ollama.
    *   **Role:** The active orchestrator. It polls the Broker for pending requests, establishes a direct SSH link to the Client, fetches context, performs inference, and updates the Client state.

---

## 2. Technical Communication Flow

### Step A: Client Registration
1.  The Client VM runs an autonomous agent.
2.  It generates a **UUID** and gathers its local connection metadata (IP, SSH Public Key).
3.  It registers with the **Broker** via `POST /register/ssh`.
4.  The Broker saves this to `rangecrawler.db`.

### Step B: The Worker Polling Loop
1.  The **Ollama Worker** polls the Broker: `GET /work/pending`.
2.  The Broker returns the connection details for a Client requesting service.
3.  The Worker establishes a **Direct SSH Connection** to the Client VM.

### Step C: Stateful Inference
1.  **Sync:** The Worker downloads `context.json` from the Client VM to memory.
2.  **Process:** The Worker receives the prompt (either from the Broker or via a local Client trigger).
3.  **Generate:** Ollama generates a response or determines tool use.
4.  **Execute:** If the LLM requests a tool, the Worker executes it *directly on the Client VM* over SSH.
5.  **Update:** The Worker pushes the updated `context.json` back to the Client VM.
6.  **Persistence:** If the network drops, the Client still has its full history. The next Worker can resume by downloading the state again.

---

## 3. Technology Stack
- **Broker:** FastAPI, Uvicorn, SQLite, Pydantic.
- **Worker:** Python, Paramiko (SSH), Ollama API, httpx.
- **Client:** Python (Agent), OpenSSH Server.
- **Deployment:** Docker Compose (Broker), Systemd (Agent/Worker).

---

## 4. Robustness & Resilience
- **State at the Edge:** Moving context to the Client VM ensures that inference is "stateless" for the Worker but "stateful" for the environment.
- **Polling vs. Webhooks:** Polling ensures the Ollama server can be behind a firewall or NAT without needing a public endpoint.
- **Atomic Updates:** Context files should be updated atomically to prevent corruption during network loss.

---

## 5. Development Priorities
1.  **Broker API:** Transition from a proxy to a registry (Endpoints for workers to claim jobs).
2.  **Context Sync Protocol:** Efficient SSH-based JSON sync (SFTP or SCP).
3.  **Worker Logic:** The logic that bridges the Broker's queue and the Ollama generation.
4.  **UUID Management:** Unique identification of Client VMs to prevent session cross-talk.
