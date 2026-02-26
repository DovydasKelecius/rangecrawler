import httpx
import argparse
import sys
import time

def main():
    parser = argparse.ArgumentParser(description="Submit an ad-hoc command to RangeCrawler.")
    parser.add_argument("command", type=str, help="The shell command to execute.")
    parser.add_argument("--ip", type=str, default="127.0.0.1", help="Target client IP (default: 127.0.0.1)")
    parser.add_argument("--broker", type=str, default="http://localhost:8000", help="Broker URL")
    parser.add_argument("--wait", action="store_true", help="Wait for result")
    
    args = parser.parse_args()
    
    try:
        # 1. Submit
        resp = httpx.post(f"{args.broker}/command/submit", json={
            "client_ip": args.ip,
            "command": args.command
        }, timeout=10.0)
        
        if resp.status_code != 200:
            print(f"[-] Error submitting: {resp.text}")
            return
        
        cmd_id = resp.json()["command_id"]
        print(f"[+] Command submitted (ID: {cmd_id}).")
        
        if args.wait:
            print("[*] Waiting for result...")
            while True:
                status_resp = httpx.get(f"{args.broker}/command/status/{cmd_id}", timeout=10.0)
                if status_resp.status_code == 200:
                    data = status_resp.json()
                    if data["status"] == "completed":
                        print("\n--- COMMAND RESULT ---")
                        print(data["result"])
                        break
                else:
                    print(f"[-] Error checking status: {status_resp.status_code}")
                    break
                time.sleep(2)

    except Exception as e:
        print(f"[-] Request failed: {e}")

if __name__ == "__main__":
    main()
