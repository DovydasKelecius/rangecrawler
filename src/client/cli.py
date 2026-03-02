import httpx
import typer
import time
import json
import os
from typing import Optional, List
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel

console = Console()
app = typer.Typer(help="RangeCrawler Client CLI: Interact with the broker and registered clients.")

STATE_FILE = os.path.expanduser("~/.rangecrawler_state.json")

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"broker_url": "http://localhost:8005"}

def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception:
        pass

@app.callback()
def main(
    ctx: typer.Context,
    broker: Optional[str] = typer.Option(None, "--broker", help="URL of the RangeCrawler broker"),
):
    state = load_state()
    if broker:
        state["broker_url"] = broker
        save_state(state)
    
    ctx.obj = state

def get_broker_url(ctx: typer.Context):
    return ctx.obj.get("broker_url", "http://localhost:8005")

@app.command()
def models(ctx: typer.Context):
    """List available models on the broker."""
    broker_url = get_broker_url(ctx)
    try:
        resp = httpx.get(f"{broker_url}/v1/models", timeout=10.0)
        if resp.status_code == 200:
            models_list = resp.json().get("data", [])
            if not models_list:
                console.print("[yellow]No models found. Ensure a worker is running and reporting models.[/yellow]")
                return

            table = Table(title=f"Available Models on {broker_url}")
            table.add_column("Model ID", style="cyan")
            table.add_column("Owned By", style="magenta")
            
            for m in models_list:
                table.add_row(m["id"], m["owned_by"])
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
            table.add_column("Workspace", style="dim")
            
            for c in clients_list:
                table.add_row(c["ip"], c["ssh_username"], c["ssh_host"], c.get("working_directory", "."))
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
    model: str = typer.Option(..., "--model", help="Model ID to use"),
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
                    timeout=300.0 # Long timeout for agent loops
                )
                
            if resp.status_code == 200:
                data = resp.json()
                assistant_msg = data["choices"][0]["message"]
                content = assistant_msg.get("content", "")
                
                # Keep history
                messages.append(assistant_msg)
                
                console.print(f"\n[bold yellow]Assistant>[/bold yellow] {content}")
            else:
                console.print(f"[bold red]Error:[/bold red] Broker returned {resp.status_code}: {resp.text}")
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")

if __name__ == "__main__":
    app()
