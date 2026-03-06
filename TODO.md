# RangeCrawler Master TODO List (Registry/Worker Architecture)

This roadmap outlines the implementation of the three-tier architecture: **Client**, **Broker**, and **Ollama Worker**.

## 1. Broker (The Registry)

_Goal: Transform the current broker into a robust state-management and job-queue system._

- [ ] **Database Schema Expansion:**
  - [ ] Add `uuid` column (Primary Key) to `allowed_ips` or new `clients` table.
  - [ ] Add `status` column (idle, pending, busy, offline).
  - [ ] Add `last_heartbeat` timestamp.
  - [ ] Add `ssh_public_key` storage.
- [ ] **Worker API Endpoints:**
  - [ ] `GET /api/v1/jobs/claim`: For Ollama workers to find a pending client request.
  - [ ] `POST /api/v1/jobs/update`: For workers to report progress or completion.
  - [ ] `GET /api/v1/clients`: List all registered clients and their status.
- [ ] **Heartbeat Monitor:**
  - [ ] Implement a background task to mark clients as "offline" if heartbeat fails for > X mins (changeable).
- [ ] **Security:**
  - [ ] Implement simple token-based auth between Worker and Broker. (When doing this TODO task, tell me more about how this is going to work, and then ask if this should be implemented!)

## 2. Client VM (The Edge State)

_Goal: Ensure the client is the master of its own conversation history._

- [ ] **Context Management:**
  - [ ] Implement `context.json` structure (role/content messages).
  - [ ] Add logic to the client agent to initialize `context.json` if missing.
  - [ ] Ensure `context.json` is readable/writable by the SSH user.
- [ ] **Self-Registration (Robust):**
  - [ ] Auto-generate a persistent UUID stored in `.rangecrawler_uuid`.
  - [ ] Implement "Heartbeat" loop to the Broker.
  - [ ] Automatically detect and report IP changes.

## 3. Ollama Worker (The Orchestrator)

_Goal: Create a standalone service that connects everything together._

- [ ] **The "Worker" Loop:**
  - [ ] Implement a polling loop (every X seconds) to query the Broker for jobs.
  - [ ] Implement job "claiming" logic to prevent multiple workers from hitting the same client.
- [ ] **Direct SSH Bridge:**
  - [ ] Implement `fetch_context()`: Download `context.json` from Client via SFTP.
  - [ ] Implement `push_context()`: Upload updated `context.json` to Client.
- [ ] **Ollama Integration:**
  - [ ] Connect to local/remote Ollama API (`/api/generate` or `/api/chat`).
  - [ ] Map the downloaded `context.json` to the Ollama prompt format.
- [ ] **Tool Execution (Remote):**
  - [ ] Logic to parse LLM output for tool calls.
  - [ ] Execute tools (bash, read, write) directly on Client VM over the _existing_ SSH session.
- [ ] **Resilience:**
  - [ ] Graceful handling of SSH disconnects.
  - [ ] Logic to "unclaim" or "fail" a job in the Broker if the worker crashes.

## 4. Testing & Robustness

- [ ] **Network Loss Simulation:** Verify that if the Worker VM is unplugged, the Client VM's `context.json` remains intact.
- [ ] **Concurrency Test:** Run 2 Client VMs and ensure the Broker and Worker keep their sessions isolated via UUID.
- [ ] **Large Context Handling:** Ensure that as `context.json` grows, the SSH transfer doesn't become a bottleneck.
- [ ] **Model Switching:** Allow the Client to request a specific model via the Broker.
