import httpx
import json
import logging
import time
from openai import OpenAI

# 1. Configuration
BROKER_URL = "http://localhost:8000"

def register_and_test():
    # 2. Register Client IP
    print(f"[*] Registering client IP at {BROKER_URL}/register...")
    try:
        resp = httpx.post(f"{BROKER_URL}/register")
        if resp.status_code == 200:
            print(f"[+] Registration result: {resp.json()}")
        else:
            print(f"[-] Registration failed with status {resp.status_code}: {resp.text}")
            return
    except Exception as e:
        print(f"[-] Registration failed: {e}")
        return

    # 3. Test Proxying to Gemini
    target_model = "gemini-2.5-flash" 
    print(f"[*] Sending request to broker for Gemini model '{target_model}'...")
    
    # Note: Broker auto-injects the API key from config.yaml
    client = OpenAI(base_url=f"{BROKER_URL}/v1", api_key="placeholder")
    
    try:
        response = client.chat.completions.create(
            model=target_model,
            messages=[{"role": "user", "content": "Hello Gemini! Say 'Success' if you can read this."}],
            stream=False
        )
        print(f"[+] Gemini response: {response.choices[0].message.content}")
    except Exception as e:
        print(f"[-] Inference failed: {e}")

if __name__ == "__main__":
    register_and_test()
