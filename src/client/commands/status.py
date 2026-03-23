import httpx
from rich.console import Console
from rich.panel import Panel

console = Console()

def show_status(broker_url: str, state_file: str):
    console.print(Panel(
        f"[bold blue]Active Broker:[/bold blue] {broker_url}\n"
        f"[bold green]State File:[/bold green] {state_file}",
        title="RangeCrawler Client Status"
    ))
    
    try:
        resp = httpx.get(f"{broker_url}/health", timeout=5.0)
        if resp.status_code == 200:
            console.print("[bold green]✓ Broker is ONLINE[/bold green]")
            
            models_resp = httpx.get(f"{broker_url}/v1/models", timeout=5.0)
            if models_resp.status_code == 200:
                models = models_resp.json().get("data", [])
                if models:
                    console.print("\n[bold cyan]Permitted Models:[/bold cyan]")
                    for m in models: console.print(f" - {m['id']}")
                else:
                    console.print("\n[yellow]! No models currently permitted.[/yellow]")
        else:
            console.print(f"[bold red]✗ Broker error {resp.status_code}[/bold red]")
    except Exception as e:
        console.print(f"[bold red]✗ Could not reach broker: {e}[/bold red]")
