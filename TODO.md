# RangeCrawler Agent Roadmap

## Phase 1: Core Agent Implementation (Current)

- [ ] Implement `LocalTools` class in `manager.py` for system access.
- [ ] `read_file`: Read file contents.
- [ ] `write_file`: Overwrite file contents.
- [ ] `append_to_file`: Append to file contents.
- [ ] `list_directory`: List files in a path.
- [ ] `run_bash`: Execute shell commands with timeout.
- [ ] `get_current_directory`: Identify working directory.
- [ ] Define OpenAI-compatible JSON schemas for all tools.
- [ ] Implement the **Recursive Agent Loop** in `server.py`.
- [ ] Detect `tool_calls` in LLM response.
- [ ] Dispatch to local Python functions.
- [ ] Maintain conversation history with `tool` roles.
- [ ] Implement iteration limit (max 15) to prevent infinite loops.
- [ ] Add robust error handling for tool failures (reporting back to LLM).

## Phase 2: Session & Environment Management

- [ ] **Isolated Working Directories**: Create a unique, persistent folder for each session/IP to prevent cross-contamination.
- [ ] **Stateful Shells**: Maintain shell session state (env vars, `cd` persistence) between `run_bash` calls.
- [ ] **Parallel Tool Execution**: Support executing multiple independent `tool_calls` in a single turn.

## Phase 3: Resource & Security Controls (Cyber Range Ready)

- [ ] **Token Budgets**: Set per-session limits on total tokens used by the agent.
- [ ] **Time-based Access**: Auto-expire agent sessions after a configured duration.
- [ ] **Sandboxed Execution**: (Future) Transition `run_bash` to a Docker or Firecracker container.

## Phase 4: Advanced Capabilities

- [ ] **Streaming Support**: Implement intermediate tool result streaming to the client.
- [ ] **File I/O via API**: Allow users to upload/download files directly to the agent's working directory.
- [ ] **Multi-Backend Support**: Seamlessly switch between Gemini, local vLLM, and Ollama.
