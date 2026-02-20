# RangeCrawler: GEMINI context

RangeCrawler is a portable, secure brokerage system for LLM inference. It acts as a smart router and dynamic loader for vLLM instances, allowing multiple models to be served on a single GPU by loading them on-demand and unloading them when idle.

## Project Overview

- **Purpose:** Provide an OpenAI-compatible API that manages the lifecycle of multiple LLM models on shared GPU resources.
- **Core Functionality:**
    - **Dynamic Model Loading:** Models are started (via vLLM) only when first requested.
    - **Smart Routing:** Intercepts `/v1/completions` and `/v1/chat/completions` requests and routes them to the correct backend instance.
    - **Idle Management:** Automatically shuts down model instances after a period of inactivity to free up VRAM.
    - **GPU Cache Management:** Explicitly clears the GPU cache after unloading a model to prevent memory fragmentation.
    - **Request Queuing:** Gracefully handles incoming requests while a model is being loaded.

## Architecture & Tech Stack

- **Framework:** [FastAPI](https://fastapi.tiangolo.com/) for the main broker API.
- **Inference Engine:** [vLLM](https://github.com/vllm-project/vllm) for high-performance model serving.
- **Proxying:** [httpx](https://www.python-httpx.org/) for asynchronous request forwarding and streaming support.
- **Configuration:** [PyYAML](https://pyyaml.org/) and [Pydantic](https://docs.pydantic.dev/) for structured settings.
- **GPU Management:** [PyTorch](https://pytorch.org/) for cache management.

### Key Components

- `src/main.py`: Entry point for the application.
- `src/broker/server.py`: FastAPI server implementing the OpenAI-compatible API.
- `src/broker/manager.py`: Core logic for managing vLLM processes, ports, and lifecycle states.
- `src/broker/config.py`: Configuration loading and validation.
- `src/broker/models.py`: Pydantic data models for tracking instance states.

## Building and Running

### Prerequisites
- Python 3.10+
- CUDA-compatible GPU and drivers.
- `torch` and `vLLM` installed with CUDA support.

### Commands
- **Install Dependencies:**
  ```bash
  pip install -r requirements.txt
  ```
- **Run Broker:**
  ```bash
  python src/main.py --mode broker
  ```
- **Configuration:**
  Edit `config.yaml` to define allowed models and resource limits (e.g., `gpu_memory_utilization`).

## Development Conventions

- **Async First:** All network and management operations should be asynchronous using `asyncio` and `httpx.AsyncClient`.
- **Model Whitelisting:** The broker only allows loading models explicitly defined in `config.yaml` for security and resource control.
- **Logging:** Use the project-wide logger (configured via `config.yaml`). Log key lifecycle events (loading, ready, unloading, errors).
- **Error Handling:** Ensure that failed model startups are caught, instances are cleaned up, and pending requests are notified/failed gracefully.
- **Resource Discipline:** Always verify that `gpu_memory_utilization` settings allow for the desired number of concurrent models.

## Usage Example

```python
from openai import OpenAI

# The broker intercepts this and loads 'facebook/opt-125m' if not already running
client = OpenAI(base_url="http://localhost:8000/v1", api_key="range-crawler")

response = client.chat.completions.create(
    model="facebook/opt-125m",
    messages=[{"role": "user", "content": "Explain quantum entanglement."}]
)
```
