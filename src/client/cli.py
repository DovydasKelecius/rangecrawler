import httpx
import typer
import time
import json
import os
import base64
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live

console = Console()
app = typer.Typer(help="RangeCrawler Client CLI: Interact with the broker and registered clients.")

# State file location
STATE_FILE = os.path.expanduser("~/.rangecrawler_state.json")

def load_state():
    """Load the persisted client state."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception: # nosec B110
            pass
    return {"broker_url": "http://localhost:8000"}

def save_state(state):
    """Save the client state to disk."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        console.print(f"[dim red]Warning: Could not save state: {e}[/dim red]")

@app.callback()
def main(
    ctx: typer.Context,
    broker: Optional[str] = typer.Option(None, "--broker", help="URL of the RangeCrawler broker"),
):
    """
    Client CLI entry point. Loads state and overrides with --broker if provided.
    """
    state = load_state()
    if broker:
        # If user provides a broker URL, save it as the new default
        state["broker_url"] = broker
        save_state(state)
    
    ctx.obj = state

def get_broker_url(ctx: typer.Context):
    # Ensure it doesn't have a trailing slash
    url = ctx.obj.get("broker_url", "http://localhost:8000")
    return url.rstrip("/")

@app.command()
def status(ctx: typer.Context):
    """Show current client configuration and connectivity."""
    broker_url = get_broker_url(ctx)
    
    console.print(Panel(
        f"[bold blue]Active Broker:[/bold blue] {broker_url}\n"
        f"[bold green]State File:[/bold green] {STATE_FILE}",
        title="RangeCrawler Client Status"
    ))
    
    try:
        resp = httpx.get(f"{broker_url}/health", timeout=5.0)
        if resp.status_code == 200:
            console.print("[bold green]✓ Broker is ONLINE[/bold green]")
            
            # List models permitted for this client
            models_resp = httpx.get(f"{broker_url}/v1/models", timeout=5.0)
            if models_resp.status_code == 200:
                models = models_resp.json().get("data", [])
                if models:
                    console.print("\n[bold cyan]Permitted Models:[/bold cyan]")
                    for m in models:
                        console.print(f" - {m['id']}")
                else:
                    console.print("\n[yellow]! No models currently permitted for your IP.[/yellow]")
        else:
            console.print(f"[bold red]✗ Broker returned error {resp.status_code}[/bold red]")
    except Exception as e:
        console.print(f"[bold red]✗ Could not reach broker: {e}[/bold red]")

@app.command()
def chat(
    ctx: typer.Context,
    model: str = typer.Option(..., "--model", help="Model ID to use (e.g. llama3:latest)"),
):
    """Start an interactive chat session with the Broker's Agent."""
    broker_url = get_broker_url(ctx)
    
    # 1. Verify model access before starting
    try:
        models_resp = httpx.get(f"{broker_url}/v1/models", timeout=5.0)
        permitted = [m["id"] for m in models_resp.json().get("data", [])]
        if model not in permitted:
            console.print(f"[bold red]Error:[/bold red] You do not have permission to use model '{model}'.")
            return
    except Exception as e:
        console.print(f"[bold red]Error verifying access:[/bold red] {e}")
        return

    console.print(Panel(f"Model: [bold green]{model}[/bold green]\n"
                        f"Type 'exit' or 'quit' to end.", title="RangeCrawler Agent Chat"))
    
    messages = []
    
    while True:
        try:
            user_input = console.input("[bold cyan]User> [/bold cyan]")
            if user_input.lower() in ["exit", "quit"]:
                break
            
            messages.append({"role": "user", "content": user_input})
            
            with console.status(f"[bold blue]Agent is thinking (wall-clock timer active)...") as status:
                resp = httpx.post(
                    f"{broker_url}/v1/chat/completions",
                    json={
                        "model": model,
                        "messages": messages,
                        "stream": False
                    },
                    timeout=300.0 # Agents can take a long time
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    assistant_msg = data["choices"][0]["message"]
                    messages.append(assistant_msg)
                    console.print(f"\n[bold yellow]Assistant>[/bold yellow] {assistant_msg['content']}\n")
                else:
                    err = resp.json().get("detail", "Unknown error")
                    console.print(f"[bold red]Error ({resp.status_code}):[/bold red] {err}")
                    messages.pop() # Remove failed message
        except KeyboardInterrupt:
            break
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")

@app.command()
def provision(
    ctx: typer.Context,
    model: str = typer.Argument(..., help="The model to provision (e.g. gpt-4o)"),
    timeout: int = typer.Option(30, "--timeout", help="Provisioning timeout in minutes")
):
    """Request a local Ollama API tunnel on localhost:11434."""
    broker_url = get_broker_url(ctx)
    try:
        resp = httpx.post(
            f"{broker_url}/v1/request-ollama",
            json={"model": model, "timeout_minutes": timeout},
            timeout=10.0
        )
        if resp.status_code == 200:
            console.print(Panel(resp.json()["message"], title="Provisioning Started", border_style="green"))
        else:
            err = resp.json().get("detail", "Provisioning failed")
            console.print(f"[bold red]Error ({resp.status_code}):[/bold red] {err}")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

if __name__ == "__main__":
    app()
