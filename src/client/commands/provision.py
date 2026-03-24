import httpx
from rich.console import Console
from rich.panel import Panel

console = Console()

def request_provision(broker_url: str, model: str, timeout: int):
    try:
        resp = httpx.post(f"{broker_url}/v1/request-ollama", json={"model": model, "timeout_minutes": timeout}, timeout=10.0)
        if resp.status_code == 200:
            console.print(Panel(resp.json()["message"], title="Provisioning Started", border_style="green"))
        else:
            console.print(f"[bold red]Error ({resp.status_code}):[/bold red] {resp.text}")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
