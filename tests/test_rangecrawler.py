import httpx

# --- Configuration ---
BROKER_URL = "http://127.0.0.1:8000"
TARGET_MODEL = "gemini-2.5-flash" 

def run_test():
    print(f"[*] Connecting to RangeCrawler at {BROKER_URL}...")
    
    # 1. Register your IP
    try:
        register_url = f"{BROKER_URL}/register"
        print(f"[*] Registering IP at {register_url}...")
        resp = httpx.post(register_url, timeout=5.0)
        if resp.status_code == 200:
            print("[+] Registration successful.")
        else:
            print(f"[-] Registration failed: {resp.text}")
            return
    except Exception as e:
        print(f"[-] Could not connect to broker: {e}")
        return

    # 2. Agent Test
    print(f"\n[*] TESTING AGENT AUTONOMY (Model: {TARGET_MODEL})")
    
    # Using a raw httpx request so we can see the custom headers
    payload = {
        "model": TARGET_MODEL,
        "messages": [
            {"role": "user", "content": "List the files, current OS distribution or something I can differentiate the systems by (like ip), read them and output to the 'agent_summary.txt', do a sentence each on what it does like /init and write 'agent_summary.txt'. Iteratie until every file is read and written about, create a todo list if needed. Done."}
        ],
        "stream": False
    }
    
    try:
        resp = httpx.post(f"{BROKER_URL}/v1/chat/completions", json=payload, timeout=300.0)
        
        # Check custom agent headers
        agent_header = resp.headers.get("X-RangeCrawler-Agent")
        
        response_data = resp.json()
        fingerprint = response_data.get("system_fingerprint")
        
        print("\n[+] VERIFYING AGENT SIGNATURE:")
        print(f"    Header 'X-RangeCrawler-Agent': {agent_header}")
        print(f"    System Fingerprint: {fingerprint}")
        
        print("\n[+] FINAL AGENT RESPONSE:")
        print("-" * 50)
        print(response_data["choices"][0]["message"]["content"])
        print("-" * 50)
        
        print("\n[!] Note: agent_summary.txt is INSIDE the container.")
        print("    Check with: docker exec $(docker ps -q --filter ancestor=rangecrawler-broker) cat /app/agent_summary.txt")
            
    except Exception as e:
        print(f"\n[-] Agent Loop failed: {e}")

if __name__ == "__main__":
    run_test()
