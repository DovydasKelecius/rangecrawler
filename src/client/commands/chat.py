import httpx
from rich.console import Console
from rich.panel import Panel

console = Console()

def start_chat(broker_url: str, model: str):
    try:
        models_resp = httpx.get(f"{broker_url}/v1/models", timeout=5.0)
        permitted = [m["id"] for m in models_resp.json().get("data", [])]
        if model not in permitted:
            console.print(f"[bold red]Error:[/bold red] No permission for '{model}'.")
            return
    except Exception as e:
        console.print(f"[bold red]Error verifying access:[/bold red] {e}")
        return

    console.print(Panel(f"Model: [bold green]{model}[/bold green]", title="Agent Chat"))
    messages = []
    while True:
        try:
            user_input = console.input("[bold cyan]User> [/bold cyan]")
            if user_input.lower() in ["exit", "quit"]:
                break
            messages.append({"role": "user", "content": user_input})
            with console.status("[bold blue]Agent is thinking..."):
                resp = httpx.post(f"{broker_url}/v1/chat/completions", json={"model": model, "messages": messages}, timeout=300.0)
                if resp.status_code == 200:
                    assistant_msg = resp.json()["choices"][0]["message"]
                    messages.append(assistant_msg)
                    console.print(f"\n[bold yellow]Assistant>[/bold yellow] {assistant_msg['content']}\n")
                else:
                    console.print(f"[bold red]Error ({resp.status_code}):[/bold red] {resp.text}")
                    messages.pop()
        except KeyboardInterrupt:
            break
