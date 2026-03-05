import httpx
import typer
import time
import json
import os
from typing import Optional, List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

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
        except Exception:
            pass
    return {"broker_url": "http://localhost:8005"}

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
    return ctx.obj.get("broker_url", "http://localhost:8005")

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
        else:
            console.print(f"[bold red]✗ Broker returned error {resp.status_code}[/bold red]")
    except Exception as e:
        console.print(f"[bold red]✗ Could not reach broker: {e}[/bold red]")

@app.command()
def models(ctx: typer.Context):
    """List available models discovered via Ollama /api/tags."""
    broker_url = get_broker_url(ctx)
    try:
        resp = httpx.get(f"{broker_url}/v1/models", timeout=10.0)
        if resp.status_code == 200:
            models_list = resp.json().get("data", [])
            if not models_list:
                console.print("[yellow]No models found. Ensure a worker is running and reporting Ollama models.[/yellow]")
                return

            table = Table(title=f"Available Models on {broker_url}")
            table.add_column("Model Name (ID)", style="cyan")
            table.add_column("Source", style="magenta")
            
            for m in models_list:
                table.add_row(m["id"], m.get("owned_by", "worker"))
            console.print(table)
        else:
            console.print(f"[bold red]Error:[/bold red] Broker returned {resp.status_code}")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] Could not connect to broker: {e}")

@app.command()
def clients(ctx: typer.Context):
    """List registered clients on the broker."""
    broker_url = get_broker_url(ctx)
    try:
        resp = httpx.get(f"{broker_url}/clients", timeout=10.0)
        if resp.status_code == 200:
            clients_list = resp.json().get("clients", [])
            if not clients_list:
                console.print("[yellow]No clients registered.[/yellow]")
                return

            table = Table(title="Registered Clients")
            table.add_column("IP", style="green")
            table.add_column("User", style="yellow")
            table.add_column("SSH Host", style="blue")
            
            for c in clients_list:
                table.add_row(c["ip"], c["ssh_username"], c["ssh_host"])
            console.print(table)
        else:
            console.print(f"[bold red]Error:[/bold red] Broker returned {resp.status_code}")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] Could not connect to broker: {e}")

@app.command()
def run(
    ctx: typer.Context,
    command: str = typer.Argument(..., help="The shell command to execute"),
    ip: str = typer.Option(..., "--ip", help="IP of the target client"),
    wait: bool = typer.Option(True, help="Wait for the result"),
):
    """Run an ad-hoc command on a remote client."""
    broker_url = get_broker_url(ctx)
    try:
        resp = httpx.post(
            f"{broker_url}/command/submit",
            json={"client_ip": ip, "command": command},
            timeout=10.0
        )
        if resp.status_code == 200:
            cmd_id = resp.json().get("command_id")
            console.print(f"[bold green]✓[/bold green] Command submitted (ID: {cmd_id})")
            
            if wait:
                with console.status("[bold blue]Waiting for result...") as status:
                    while True:
                        status_resp = httpx.get(f"{broker_url}/command/status/{cmd_id}", timeout=5.0)
                        if status_resp.status_code == 200:
                            data = status_resp.json()
                            if data["status"] == "completed":
                                console.print("\n[bold]Command Result:[/bold]")
                                console.print(Panel(data["result"], border_style="dim"))
                                break
                        time.sleep(2)
        else:
            console.print(f"[bold red]Error:[/bold red] Submission failed ({resp.status_code})")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command()
def chat(
    ctx: typer.Context,
    model: str = typer.Option(..., "--model", help="Model ID to use (e.g. llama3:latest)"),
    system: str = typer.Option("You are a helpful assistant with access to a Linux terminal.", "--system", help="System prompt"),
):
    """Start an interactive chat session with a model through the broker agent loop."""
    broker_url = get_broker_url(ctx)
    messages = [{"role": "system", "content": system}]
    
    console.print(f"[bold blue]Starting session with {model} via {broker_url}. Type 'exit' or 'quit' to end.[/bold blue]")
    
    while True:
        user_input = console.input("[bold green]User> [/bold green]")
        if user_input.lower() in ["exit", "quit"]:
            break
        
        messages.append({"role": "user", "content": user_input})
        
        try:
            with console.status(f"[bold blue]Agent is thinking (using {model})..."):
                resp = httpx.post(
                    f"{broker_url}/v1/chat/completions",
                    json={"model": model, "messages": messages},
                    timeout=300.0 
                )
                
            if resp.status_code == 200:
                data = resp.json()
                assistant_msg = data["choices"][0]["message"]
                content = assistant_msg.get("content", "")
                
                messages.append(assistant_msg)
                console.print(f"\n[bold yellow]Assistant>[/bold yellow] {content}")
            else:
                console.print(f"[bold red]Error:[/bold red] Broker returned {resp.status_code}: {resp.text}")
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")

if __name__ == "__main__":
    app()
