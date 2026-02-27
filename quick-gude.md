
  ---
  
  1. Start the System (Server Side)
  Ensure the Broker and Worker containers are running on their respective VMs.


   1 # On Broker VM:
   2 docker compose up -d broker
   3
   4 # On Worker VM:
   5 docker compose up -d worker

  ---

  2. Connect your Client (The VM you want to control)
  Run the agent script on your Client VM. It will automatically authorize the
  worker and register with the broker.


   1 # On Client VM:
   2 sudo ./venv/bin/python src/agent/headless_client.py --broker
     http://<BROKER_IP>:8000 --user root --dir /tmp

  ---


  3. Option A: Run a Manual Command (Ad-Hoc)
  If you want to run a specific shell command on the Client VM from anywhere (using
  the provided utility):
   1 # On any VM with the repository:
   2 ./venv/bin/python submit_command.py "ls -la /root" --ip <CLIENT_IP> --wait
  Note: Use the IP that the client registered with (e.g., `172.18.0.1` for local
  docker tests).

  ---

  4. Option B: Chat with Ollama (AI Interaction)
  The system is designed to "watch" the Client VM for new prompts. To start a
  conversation:


   1 # On Client VM:
   2 echo "Hello AI, what is my current OS version?" > /tmp/prompt.txt
  What happens next:
   1. The Worker sees prompt.txt.
   2. It downloads /tmp/context.json (if it exists) to get your history.
   3. It asks Ollama for the answer.
   4. It uploads the updated /tmp/context.json back to your Client VM.
   5. It deletes prompt.txt to signify it is finished.

  ---


  5. Checking Status and Monitoring
  To see what the system is "thinking" or if everything is connected:


   * View Registry: curl -s http://<BROKER_IP>:8000/clients | jq
   * Watch Worker Brain: docker logs -f rangecrawler-worker-1
   * Check AI Context: cat /tmp/context.json (On the Client VM).


  Summary of Files on Client VM:
   * /tmp/prompt.txt: Write your question here to trigger the AI.
   * /tmp/context.json: This is the Source of Truth. Your entire conversation
     history lives here and stays here.