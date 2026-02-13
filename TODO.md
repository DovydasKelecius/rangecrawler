# RangeCrawler Development TODO

## Phase 1: Core Infrastructure
- [x] Define Pydantic schemas for internal state and API communication (`src/broker/models.py`)
- [x] Implement `ModelManager` for lifecycle management of vLLM instances (`src/broker/manager.py`)
    - [x] Process management (subprocess.Popen)
    - [x] Port allocation logic
    - [x] Health checking for new instances
    - [x] Idle unloading & GPU cache clearing
- [x] Implement FastAPI Broker Server (`src/broker/server.py`)
    - [x] `/v1/models` endpoint
    - [x] `/v1/completions` proxy/routing
    - [x] `/v1/chat/completions` proxy/routing

## Phase 2: Reliability & Polishing
- [x] Add robust error handling for vLLM startup failures
- [x] Implement request queuing/concurrency limits per model
- [x] Add structured logging
- [x] Configuration management (YAML/Environment variables)

## Phase 3: Client & Documentation
- [x] Create example headless client (`src/agent/headless_client.py`)
- [x] Write `requirements.txt`
- [x] Update `README.md` with setup and usage instructions
