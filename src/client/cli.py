import typer
import os
import json
import httpx
import time
from typing import Optional
from dotenv import load_dotenv
from .commands.status import show_status
from .commands.chat import start_chat
from .commands.provision import request_provision

load_dotenv()

app = typer.Typer(help="RangeCrawler Client CLI.")
STATE_FILE = os.path.expanduser("~/.rangecrawler_state.json")

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f: return json.load(f)
        except: pass
    return {"broker_url": os.getenv("BROKER_URL", "http://localhost:8005")}

def save_state(state):
    with open(STATE_FILE, "w") as f: json.dump(state, f)

@app.callback()
def main(ctx: typer.Context, broker: Optional[str] = typer.Option(None, "--broker")):
    state = load_state()
    if broker:
        state["broker_url"] = broker
        save_state(state)
    ctx.obj = state

@app.command()
def status(ctx: typer.Context):
    show_status(ctx.obj["broker_url"], STATE_FILE)

@app.command()
def chat(ctx: typer.Context, model: str = typer.Option(..., "--model")):
    start_chat(ctx.obj["broker_url"], model)

@app.command()
def provision(ctx: typer.Context, model: str = typer.Argument(...), timeout: int = typer.Option(30)):
    request_provision(ctx.obj["broker_url"], model, timeout)

@app.command()
def run(ctx: typer.Context, command: str = typer.Argument(...), ip: str = typer.Option(..., "--ip")):
    """Run a shell command on a remote client."""
    broker_url = ctx.obj["broker_url"]
    try:
        resp = httpx.post(f"{broker_url}/command/submit", json={"client_ip": ip, "command": command}, timeout=10.0)
        if resp.status_code == 200:
            cmd_id = resp.json()["command_id"]
            typer.echo(f"Command submitted. ID: {cmd_id}. Waiting for result...")
            while True:
                status_resp = httpx.get(f"{broker_url}/command/status/{cmd_id}")
                if status_resp.status_code == 200:
                    data = status_resp.json()
                    if data["status"] == "completed":
                        typer.echo(f"\nResult:\n{data['result']}")
                        break
                time.sleep(2)
        else:
            typer.echo(f"Error: {resp.text}")
    except Exception as e:
        typer.echo(f"Error: {e}")
