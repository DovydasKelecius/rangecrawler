import httpx
import json
import logging
from openai import OpenAI

# 1. Configuration
BROKER_URL = "http://localhost:8000"
# Use your Gemini API key here
API_KEY = "your-gemini-api-key"

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

    # 3. Test Proxying
    # Set model to whatever you configured in config.yaml (e.g., gemini-1.5-flash)
    target_model = "gemini-1.5-flash" 
    print(f"[*] Sending request to broker for model '{target_model}'...")
    
    # The broker forwards the api_key to the remote_url
    client = OpenAI(base_url=f"{BROKER_URL}/v1", api_key=API_KEY)
    
    try:
        response = client.chat.completions.create(
            model=target_model,
            messages=[{"role": "user", "content": "Hello, are you working through the RangeCrawler proxy?"}],
            stream=False
        )
        print(f"[+] Response content: {response.choices[0].message.content}")
    except Exception as e:
        print(f"[-] Inference failed: {e}")

if __name__ == "__main__":
    register_and_test()
