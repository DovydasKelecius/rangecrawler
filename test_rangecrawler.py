import httpx
from openai import OpenAI
import sys

# --- Configuration ---
BROKER_URL = "http://127.0.0.1:8005"
# Synchronized with config.yaml
TARGET_MODEL = "gemini-2.0-flash" 

def run_test():
    print(f"[*] Connecting to RangeCrawler at {BROKER_URL}...")
    
    # 1. Register your IP (Mandatory for security)
    try:
        register_url = f"{BROKER_URL}/register"
        print(f"[*] Registering IP at {register_url}...")
        resp = httpx.post(register_url, timeout=5.0)
        if resp.status_code == 200:
            print(f"[+] Registration successful: {resp.json()}")
        else:
            print(f"[-] Registration failed ({resp.status_code}): {resp.text}")
            return
    except Exception as e:
        print(f"[-] Could not connect to broker: {e}")
        return

    # 2. Send Test Request
    print(f"[*] Sending test request for model '{TARGET_MODEL}'...")
    client = OpenAI(base_url=f"{BROKER_URL}/v1", api_key="not-needed")
    
    try:
        response = client.chat.completions.create(
            model=TARGET_MODEL,
            messages=[{"role": "user", "content": "Hello! Confirm if RangeCrawler is proxying correctly."}],
            stream=False
        )
        print("\n[+] SUCCESS! Response from LLM:")
        print("-" * 40)
        print(response.choices[0].message.content)
        print("-" * 40)
        
    except Exception as e:
        print(f"\n[-] Inference failed: {e}")

if __name__ == "__main__":
    run_test()
