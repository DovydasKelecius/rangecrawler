# RangeCrawler

RangeCrawler is a portable, secure brokerage system for LLM inference. it acts as a smart router and dynamic loader for vLLM instances, allowing you to serve multiple models on a single GPU with on-demand loading and automatic idle unloading.

## Features

- **Dynamic Model Loading**: Models are started only when first requested.
- **Smart Routing**: OpenAI-compatible API that transparently routes requests to the correct model instance.
- **Idle Unloading**: Automatically shuts down idle model instances to free up GPU memory.
- **Least-Loaded Load Balancing**: Distributes requests across multiple replicas of the same model.
- **Request Queuing**: Handles requests gracefully while a model is being loaded.
- **GPU Cache Management**: Clears GPU cache after unloading a model to prevent memory fragmentation.

## Setup

1. **Install Dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

   _Note: Ensure you have `vLLM` and `torch` installed with CUDA support._

2. **Configure Models**:
   Edit `config.yaml` to define which models are allowed and set resource limits.

3. **Start the Broker**:
   ```bash
   python src/main.py --mode broker
   ```

## Usage

Point any OpenAI-compatible client to the broker URL (default: `http://localhost:8000/v1`).

### Example (Python)

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="range-crawler")

# This will trigger the loading of the model if not already running
response = client.chat.completions.create(
    model="facebook/opt-125m",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)
```

## Configuration (`config.yaml`)

- `broker`:
  - `port`: Port for the broker server.
  - `gpu_memory_utilization`: Fraction of GPU memory for each vLLM instance (e.g., `0.45` allows two instances on one GPU).
  - `idle_timeout`: Seconds of inactivity before a model is unloaded.
- `models`: List of models allowed to be loaded on-demand.

## License

MIT
