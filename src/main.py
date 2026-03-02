import typer
import uvicorn
import httpx
import logging
import os
from typing import Optional
from src.broker.config import load_config

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
    
    # Import inside command to avoid eager initialization
    from src.broker.server import app as broker_app, manager
    
    typer.echo(f"Starting Broker on {listen_host}:{listen_port} (reload={reload})")
    try:
        uvicorn.run(broker_app, host=listen_host, port=listen_port, reload=reload)
    finally:
        manager.cleanup()

@app.command()
def agent(
    broker_url: str = typer.Option("http://localhost:8000", "--broker", help="URL of the RangeCrawler broker"),
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
    if not success:
        raise typer.Exit(code=1)

@app.command()
def worker(
    broker_url: Optional[str] = typer.Option(None, envvar="BROKER_URL", help="URL of the RangeCrawler broker"),
    ollama_url: Optional[str] = typer.Option(None, envvar="OLLAMA_URL", help="URL of the Ollama server"),
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

from src.client.cli import app as client_app
app.add_typer(client_app, name="client")

if __name__ == "__main__":
    app()
