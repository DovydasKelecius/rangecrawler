# RangeCrawler: Secure Reverse Proxy context

RangeCrawler is a minimalist, secure reverse-proxy system for LLM inference. It is designed to act as a secure gateway for routing, whitelisting, and monitoring LLM requests across local and remote endpoints (including OpenAI and Gemini compatible APIs).

## Core Features & Workflow

- **Dynamic Port Assignment**: At startup, the broker can query an external endpoint to obtain its assigned listen port, allowing for easy integration into dynamic environments.
- **IP Whitelisting**: Mandatory registration via `/register`. All other requests from non-registered IPs are rejected with a `403 Forbidden`.
- **Transparent Proxying**: Intercepts OpenAI-compatible chat and completion requests and forwards them to the target remote endpoints.
- **SSH Tunneling**: Automatically establishes and reuses SSH tunnels for remote vLLM instances that are behind firewalls.
- **Resource Monitoring**: Tracks session stats (IP, last active time, and token usage) as a hook for future budgeting and time-based access control.

## Project Structure

- `src/main.py`: Entry point; handles dynamic port assignment and server launch.
- `src/broker/server.py`: FastAPI server implementing the reverse proxy and security middleware.
- `src/broker/manager.py`: Core logic for IP registration, endpoint resolution, and SSH tunnel management.
- `src/broker/models.py`: Pydantic models for configuration and session tracking.
- `src/broker/config.py`: Configuration loading and validation.
- `config.yaml`: Central source of truth for all settings (models, auth, broker).

## Tech Stack

- **Framework**: FastAPI + Uvicorn
- **Client**: httpx (for async proxying)
- **Tunnelling**: sshtunnel (Paramiko based)
- **Validation**: Pydantic v2

## Running the Project

### Prerequisites
- Python 3.10+
- Requirements: `pip install -r requirements.txt`

### Local Development
```bash
# Set PYTHONPATH to include the project root
export PYTHONPATH=$PYTHONPATH:.
# Start the broker
python src/main.py --mode broker
```

### Configuration (`config.yaml`)
Control your models and security settings directly from the YAML file:
```yaml
broker:
  host: "127.0.0.1"
  default_port: 8000
models:
  - id: "gemini-1.5-flash"
    remote_url: "https://generativelanguage.googleapis.com/v1beta/openai/"
auth:
  gemini_api_key: "YOUR_KEY_HERE"
```

## Security & Best Practices

1. **IP Pinning**: The broker defaults to listening on `127.0.0.1` unless configured otherwise.
2. **Whitelist First**: Clients MUST call `/register` before they can send inference requests.
3. **Key Injection**: The broker can auto-inject API keys (like Gemini) into forwarded requests, keeping them hidden from the final client.
4. **Minimal Dependencies**: All local GPU-heavy dependencies (torch, vLLM) have been removed from the broker to keep it lightweight.
