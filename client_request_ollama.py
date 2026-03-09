import httpx
import time
import sys
import os

BROKER_URL = os.getenv("BROKER_URL", "http://localhost:8005")

def request_ollama(model_name: str):
    """Request a secure inference tunnel from the broker."""
    print(f"[*] Requesting localized Ollama ({model_name}) from Broker...")
    
    try:
        resp = httpx.post(
            f"{BROKER_URL}/v1/request-ollama",
            json={"model": model_name, "timeout_minutes": 60},
            timeout=10.0
        )
        if resp.status_code == 200:
            print(f"[+] Broker Response: {resp.json().get('message')}")
            print("[*] Waiting for tunnel establishment (approx 10s)...")
            time.sleep(10)
            return True
        else:
            print(f"[-] Request failed ({resp.status_code}): {resp.text}")
            return False
    except Exception as e:
        print(f"[-] Connection error: {e}")
        return False

def test_inference(model_name: str):
    """Attempt to use the local tunnel for inference."""
    print(f"[*] Testing local Ollama API (localhost:11434) with model: {model_name}...")

    # Example Chat request (Ollama API style)
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "What is the capital of France?"}],
        "stream": False
    }

    try:
        resp = httpx.post("http://localhost:11434/api/chat", json=payload, timeout=60.0)
        if resp.status_code == 200:
            result = resp.json()
            if "message" in result:
                print(f"[+] Inference Success: {result['message']['content']}")
            else:
                print(f"[-] Unexpected response format: {result}")
        else:
            print(f"[-] Inference failed ({resp.status_code}): {resp.text}")

        # Test whitelisting: try to PULL a model (should be BLOCKED)
        print("[*] Testing Security (Trying to PULL a new model)...")
        pull_resp = httpx.post("http://localhost:11434/api/pull", json={"name": "mistral"})
        print(f"[!] Security Status: {pull_resp.status_code} - {pull_resp.text}")
        if pull_resp.status_code == 403:
            print("[✓] SUCCESS: Security proxy blocked the forbidden request.")

    except Exception as e:
        print(f"[-] Error during testing: {e}")
        print("[TIP] Ensure the SSH tunnel is active and the Worker has Ollama running.")

if __name__ == "__main__":
    requested_model = sys.argv[1] if len(sys.argv) > 1 else "llama3"

    if request_ollama(requested_model):
        test_inference(requested_model)

