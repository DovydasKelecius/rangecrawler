import typer
import uvicorn
import httpx
import logging
import os
from typing import Optional
from src.broker.config import load_config
from src.client.cli import app as client_app

app = typer.Typer(
    help="RangeCrawler: A professional LLM brokerage and agent orchestration system.",
    add_completion=True,
)

def get_dynamic_port(url: Optional[str], default: int) -> int:
    """Fetch the assigned port from an external registration service."""
    if not url:
        return default
    try:
        resp = httpx.get(url, timeout=5.0)
        if resp.status_code == 200:
            port = int(resp.json().get("port", default))
            logging.info(f"Dynamic port assigned: {port}")
            return port
    except Exception as e:
        logging.warning(f"Failed to fetch dynamic port from {url}: {e}. Using default {default}.")
    return default

@app.callback()
def main(
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
    config_path: str = typer.Option("config.yaml", "--config", help="Path to config file"),
):
    """
    Global configuration and initialization.
    """
    # This could be used to set global state
    os.environ["RANGECRAWLER_CONFIG"] = config_path
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

@app.command()
def broker(
    host: Optional[str] = typer.Option(None, help="Host to bind the broker to"),
    port: Optional[int] = typer.Option(None, help="Port to bind the broker to"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
):
    """
    Start the RangeCrawler Broker server.
    """
    config_path = os.environ.get("RANGECRAWLER_CONFIG", "config.yaml")
    config = load_config(config_path)
    
    logging.basicConfig(
        level=getattr(logging, config.logging_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Override host/port if provided
    listen_host = host or config.broker.host
    listen_port = port or get_dynamic_port(
        config.broker.port_assignment_url, 
        config.broker.default_port
    )
    
    typer.echo(f"Starting Broker on {listen_host}:{listen_port} (reload={reload})")
    try:
        uvicorn.run("src.broker.main:app", host=listen_host, port=listen_port, reload=reload)
    except Exception as e:
        typer.echo(f"Broker failed: {e}")

@app.command()
def agent(
    broker_url: str = typer.Option(os.getenv("BROKER_URL", "http://localhost:8000"), "--broker", help="URL of the RangeCrawler broker"),
    working_dir: Optional[str] = typer.Option(None, "--dir", help="Working directory for the LLM"),
    user: Optional[str] = typer.Option(None, "--user", help="Username to register"),
    ssh_port: int = typer.Option(22, "--ssh-port", help="SSH port of this machine"),
    pkey: Optional[str] = typer.Option(None, "--pkey", help="Path to the private key ON THE BROKER"),
    heartbeat: bool = typer.Option(False, "--heartbeat", help="Run in heartbeat mode"),
):
    """
    Start the RangeCrawler Agent on a client VM.
    """
    from src.agent.headless_client import run_agent
    typer.echo(f"Starting Agent connecting to {broker_url}")
    success = run_agent(
        broker=broker_url,
        working_dir=working_dir,
        user=user,
        ssh_port=ssh_port,
        pkey=pkey,
        heartbeat=heartbeat
    )
    if success:
        # Persist this broker choice for the client CLI
        try:
            from src.client.cli import save_state, load_state
            state = load_state()
            state["broker_url"] = broker_url
            save_state(state)
            typer.echo(f"[*] Broker URL {broker_url} saved for client CLI.")
        except Exception: # nosec B110
            pass
    else:
        raise typer.Exit(code=1)

@app.command()
def worker(
    broker_url: Optional[str] = typer.Option(os.getenv("BROKER_URL", "http://localhost:8000"), envvar="BROKER_URL", help="URL of the RangeCrawler broker"),
    ollama_url: str = typer.Option(os.getenv("OLLAMA_URL", "http://localhost:11434"), envvar="OLLAMA_URL", help="URL of the Ollama server"),
):
    """
    Start the RangeCrawler Worker (Ollama orchestrator).
    """
    if broker_url:
        os.environ["BROKER_URL"] = broker_url
    if ollama_url:
        os.environ["OLLAMA_URL"] = ollama_url
        
    from src.worker.main import worker_loop
    typer.echo("Starting Worker loop...")
    worker_loop()

@app.command()
def dashboard(
    host: str = typer.Option("127.0.0.1", help="Host to bind the dashboard to"),
    port: int = typer.Option(8001, help="Port to bind the dashboard to"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
):
    """
    Start the RangeCrawler Dashboard.
    """
    typer.echo(f"Starting Dashboard on {host}:{port}")
    uvicorn.run("src.dashboard.app:app", host=host, port=port, reload=reload)

# --- ADMIN CLI ---
admin_app = typer.Typer(help="Administrative tools for managing models and permissions.")

@admin_app.command("grant")
def admin_grant(
    uuid: str = typer.Argument(..., help="Client UUID"),
    model: str = typer.Argument(..., help="Model ID"),
    broker_url: str = typer.Option(os.getenv("BROKER_URL", "http://localhost:8000"), "--broker", help="Broker URL")
):
    """Grant model access to a client."""
    payload = {
        "client_uuid": uuid,
        "model_id": model,
        "is_active": True
    }
    
    try:
        resp = httpx.post(f"{broker_url}/admin/permissions/grant", json=payload, timeout=10.0)
        if resp.status_code == 200:
            typer.echo(f"Successfully granted {model} to {uuid}")
        else:
            typer.echo(f"Error: {resp.text}")
    except Exception as e:
        typer.echo(f"Connection failed: {e}")

@admin_app.command("models")
def admin_models(
    broker_url: str = typer.Option(os.getenv("BROKER_URL", "http://localhost:8000"), "--broker", help="Broker URL")
):
    """List registered models."""
    try:
        resp = httpx.get(f"{broker_url}/admin/models", timeout=10.0)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            for m in models:
                status = "ACTIVE" if m['is_active'] else "INACTIVE"
                typer.echo(f"[{status}] {m['id']} -> {m['remote_url']}")
        else:
            typer.echo(f"Error: {resp.text}")
    except Exception as e:
        typer.echo(f"Connection failed: {e}")

@admin_app.command("permissions")
def admin_permissions(
    broker_url: str = typer.Option(os.getenv("BROKER_URL", "http://localhost:8000"), "--broker", help="Broker URL")
):
    """List all client model permissions."""
    try:
        resp = httpx.get(f"{broker_url}/admin/permissions", timeout=10.0)
        if resp.status_code == 200:
            perms = resp.json().get("permissions", [])
            typer.echo(f"{'CLIENT UUID':<40} | {'MODEL ID':<15} | {'ACTIVE':<6}")
            typer.echo("-" * 65)
            for p in perms:
                active = "YES" if p['is_active'] else "NO"
                typer.echo(f"{p['client_uuid']:<40} | {p['model_id']:<15} | {active:<6}")
        else:
            typer.echo(f"Error: {resp.text}")
    except Exception as e:
        typer.echo(f"Connection failed: {e}")

@admin_app.command("permit")
def admin_permit(
    uuid: str = typer.Argument(..., help="Agent UUID to permit"),
    permit: bool = typer.Option(True, help="Set to False to revoke permission"),
    broker_url: str = typer.Option(os.getenv("BROKER_URL", "http://localhost:8000"), "--broker", help="Broker URL")
):
    """Whitelist an agent for automatic reverse tunneling."""
    params = {"agent_uuid": uuid, "permit": permit}
    try:
        resp = httpx.post(f"{broker_url}/admin/agent/permit", params=params, timeout=10.0)
        if resp.status_code == 200:
            status = "Permitted" if permit else "Revoked"
            typer.echo(f"Successfully {status} agent {uuid}")
        else:
            typer.echo(f"Error: {resp.text}")
    except Exception as e:
        typer.echo(f"Connection failed: {e}")

@admin_app.command("agents")
def admin_agents(
    broker_url: str = typer.Option(os.getenv("BROKER_URL", "http://localhost:8000"), "--broker", help="Broker URL")
):
    """List all registered agents and their permit status."""
    try:
        resp = httpx.get(f"{broker_url}/admin/agents", timeout=10.0)
        if resp.status_code == 200:
            agents = resp.json().get("agents", [])
            typer.echo(f"{'AGENT UUID':<40} | {'HOST':<15} | {'PERMITTED':<10}")
            typer.echo("-" * 70)
            for a in agents:
                perm = "YES" if a['is_permitted'] else "NO"
                typer.echo(f"{a['uuid']:<40} | {a['ssh_host']:<15} | {perm:<10}")
        else:
            typer.echo(f"Error: {resp.text}")
    except Exception as e:
        typer.echo(f"Connection failed: {e}")

app.add_typer(admin_app, name="admin")
app.add_typer(client_app, name="client")

if __name__ == "__main__":
    app()
