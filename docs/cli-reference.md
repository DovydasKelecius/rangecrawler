# RangeCrawler: Command-Line Interface (CLI) Reference Specification

## 1. Introduction

This reference manual provides a detailed technical specification of the RangeCrawler Command-Line Interface (CLI). The system utilizes a multi-tiered CLI architecture to facilitate administrative governance and client-side resource interaction. All commands are accessible via the primary entry point, `src/main.py`.

---

## 2. Global Configuration Options

The following options are applicable to the primary execution of the system and influence global state and logging behavior.

- **`--debug`**: Enables verbose diagnostic logging (DEBUG level).
- **`--config <PATH>`**: Specifies the filesystem path to the `config.yaml` configuration file. Defaults to `config.yaml`.

---

## 3. Administrative Interface (`admin`)

The `admin` sub-command group provides governance tools for model registry auditing and client permission arbitration.

### 3.1. `admin grant`

**Description**: Authorizes a specific client IP address to access a designated LLM with optional constraints on usage and capabilities.

**Syntax**:

```bash
python3 src/main.py admin grant <IP> <MODEL> [OPTIONS]
```

**Arguments**:

- `<IP>`: The IPv4 address of the target client.
- `<MODEL>`: The unique identifier (ID) of the LLM to be authorized.

**Options**:

- **`--tools` / `--no-tools`**: Enables or disables the client's ability to execute tool-based operations (e.g., remote shell commands). Defaults to `--tools`.
- **`--quota <SECONDS>`**: Defines the maximum cumulative usage duration in seconds.
- **`--window <START-END>`**: Specifies a daily temporal window for access (e.g., `14:00-16:00`).
- **`--expires <ISO-8601>`**: Sets an absolute expiration timestamp for the permission (e.g., `2026-12-31T23:59:59`).
- **`--lease <SECONDS>`**: Defines a lease duration that commences upon the client's initial use of the model.
- **`--broker <URL>`**: Specifies the Broker's network address. Defaults to the `BROKER_URL` environment variable or `http://localhost:8000`.

**Example**:

```bash
python3 src/main.py admin grant 192.168.1.100 llama3 --quota 7200 --tools
```

### 3.2. `admin models`

**Description**: Provides a comprehensive listing of all active models registered within the Broker's database.

**Options**:

- **`--broker <URL>`**: Specifies the Broker's network address.

### 3.3. `admin permissions`

**Description**: Generates an audit report of all current client permissions, including cumulative usage metrics and remaining quotas.

**Options**:

- **`--broker <URL>`**: Specifies the Broker's network address.

---

## 4. Client Interface (`client`)

The `client` sub-command group facilitates end-user interaction with authorized models and remote workspace operations.

### 4.1. `client status`

**Description**: Displays the operational status of the client environment, the active Broker URL, and a list of models currently permitted for the client's IP.

**Syntax**:

```bash
python3 src/main.py client status
```

### 4.2. `client chat`

**Description**: Initiates a stateful, interactive session with a permitted LLM.

**Syntax**:

```bash
python3 src/main.py client chat --model <MODEL_ID>
```

**Options**:

- **`--model <MODEL_ID>`**: (Required) Specifies the model to engage with for the session.

### 4.3. `client provision`

**Description**: Requests the temporary provisioning of a dedicated LLM instance or specific resource environment.

**Syntax**:

```bash
python3 src/main.py client provision <MODEL_ID> [OPTIONS]
```

**Arguments**:

- `<MODEL_ID>`: The identifier of the model to be provisioned.

**Options**:

- **`--timeout <MINUTES>`**: Specifies the requested duration for the provisioned resource in minutes. Defaults to 30.

### 4.4. `client run`

**Description**: Dispatches a shell command for remote execution within the client's registered Agent workspace via the secure Broker tunnel.

**Syntax**:

```bash
python3 src/main.py client run <COMMAND> --ip <AGENT_IP>
```

**Arguments**:

- `<COMMAND>`: The shell command string to be executed (e.g., `"ls -la"`).

**Options**:

- **`--ip <AGENT_IP>`**: (Required) Specifies the target Agent's IP address where the command will be executed.

---

## 5. System Execution Commands

For completeness, the following commands facilitate the initialization of the core architectural components.

- **`broker`**: Initializes the central registry server.
- **`agent`**: Deploys the headless client on a target workspace machine.
- **`worker`**: Initializes the Ollama orchestration loop.
- **`dashboard`**: (Experimental) Launches the administrative web interface.

---

## 6. Conclusion

This CLI specification ensures that both administrators and clients have precise control over the RangeCrawler ecosystem. By utilizing these commands, users can effectively manage the lifecycle of distributed LLM orchestration and remote task execution.
