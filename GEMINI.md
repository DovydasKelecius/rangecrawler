# RangeCrawler: Senior Engineer Context

RangeCrawler is a portable, secure brokerage system for LLM inference. It acts as a smart router and dynamic loader for vLLM instances, facilitating on-demand serving of multiple models on single or multiple GPUs with automatic idle unloading.

## Project Overview

- **Purpose**: Secure proxy/router for LLM endpoints (Gemini, vLLM, Ollama).
- **Core Architecture**:
    - **Broker (`src/broker`)**: A FastAPI-based server that manages model configurations, handles client registration (IP whitelisting), and proxies OpenAI-compatible requests.
    - **Manager (`src/broker/manager.py`)**: Handles model loading/unloading, session management, and SSH tunneling to remote compute resources.
    - **Agent (`src/agent`)**: Includes specialized clients (e.g., `headless_client.py`) for automated interactions.
    - **Core (`src/lib.rs`)**: A Rust-based extension (via PyO3) for high-performance operations (placeholder for token counting/fast routing).
- **Key Technologies**:
    - **Python**: FastAPI, Uvicorn, Pydantic (v2), httpx, Paramiko (SSH), sshtunnel.
    - **Rust**: PyO3, Maturin.
    - **Infrastructure**: Docker & Docker Compose.

## Building and Running

### Local Environment
1. **Python Setup**:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Configuration**:
   Copy `config.example.yaml` to `config.yaml` and provide your `gemini_api_key`.
3. **Execution**:
   ```bash
   python src/main.py --mode broker --config config.yaml
   ```

### Docker (Recommended)
```bash
docker compose up --build
```
The broker listens on port `8000` by default (as configured in `docker-compose.yml` and `config.yaml`).

## Development Conventions

### Coding Style
- **Python**: Strict type hinting with Pydantic models (`src/broker/models.py`). Use `ruff` for linting and `mypy` for type checking.
- **Rust**: idiomatic Rust, exposed to Python via PyO3.
- **API**: Follows OpenAI-compatible chat completion and model listing formats.

### Security
- **Registration**: Clients must register their IP via `POST /register` before they can access model endpoints.
- **Secrets**: Never commit `config.yaml` or `.env`. Use `config.example.yaml` as a template. API keys are prioritized from environment variables (`GEMINI_API_KEY`).

### Testing
- **Client Examples**: Use `client_example.py` or `test_rangecrawler.py` to verify broker connectivity and model proxying.
- **Unit Tests**: Previously located in `tests/` (now removed for a cleaner production-ready state).

## Key Files
- `src/main.py`: Entry point for the broker.
- `src/broker/server.py`: FastAPI application and endpoint definitions.
- `src/broker/manager.py`: Core logic for model lifecycle and routing.
- `src/broker/models.py`: Pydantic schemas for configuration and state.
- `config.yaml`: Active configuration file (Host: `0.0.0.0`, Port: `8000`).
- `docker-compose.yml`: Standard deployment configuration.
