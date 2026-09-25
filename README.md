# Hermes Local

Hermes Local is a privacy-first, Windows-focused AI computer agent. This repository contains milestone 1: a safe Python application shell that starts, reports its status, and shuts down cleanly.

## Milestone boundary

The application does **not** connect to an LLM, execute arbitrary code, access files, control the computer, browse the web, persist memory, or perform retrieval. The interfaces for future capabilities are present only to establish clean ownership boundaries.

## Architecture

- `app/main.py`: CLI entry point and process lifecycle wiring.
- `app/agent/`: application orchestration. `AgentController` owns start/status/shutdown state.
- `app/models/`: provider-neutral model contracts, factory, and mock adapter. Future local or hosted adapters implement `ModelProvider`; the controller does not depend on a vendor SDK.
- `app/tools/`: explicit tool contracts and `ToolRegistry`. Tools must be registered before they can be considered by future orchestration.
- `app/security/`: policy boundary. `PermissionEngine` currently denies all requests by default.
- `app/memory/`: future bounded, auditable memory ownership.
- `app/rag/`: future retrieval boundary over approved local indexes.
- `app/config/`: typed, allowlisted environment configuration.
- `app/utils/`: shared infrastructure such as logging.
- `data/`: reserved local runtime areas for memory, RAG indexes, logs, and sandbox data.
- `tests/`: smoke tests for the foundation.

## Dependency choices

The runtime uses only the Python standard library. `pytest` is listed for development tests. Avoiding an LLM SDK and agent framework at this stage keeps startup deterministic and makes future model replacement an adapter decision rather than an architectural rewrite.

## Model providers

The agent communicates through `ModelProvider.generate(ModelRequest)` and never
calls Ollama or another vendor directly. A response may contain text,
structured data, tool-call requests, and model metadata. Provider failures use
`ModelError`, with `ModelTimeoutError` for deadlines. To add a provider, create
an adapter implementing the contract, normalize its responses, translate its
errors, and register it with `ModelProviderFactory`. No agent, tool, security,
memory, or RAG changes should be needed. The current factory only provides the
deterministic `mock` adapter; a real Ollama connection is intentionally not
implemented.

## Security boundaries

The model must never become the security boundary. Future model output will be treated as untrusted intent. The agent layer will request named tools, the registry will expose only approved tools, and the permission engine will make explicit policy decisions before execution. No unrestricted filesystem, shell, Python, PowerShell, CMD, browser, or desktop-control capability exists in this milestone.

## Configuration

Copy `.env.example` to `.env` and export those values before starting Hermes.
`HERMES_ALLOWED_FILESYSTEM_ROOTS` is required; Hermes fails closed when that
security setting is missing or unsafe. Roots are separated with `;` on Windows.
The default root is only `data/sandbox`, never the user's entire filesystem.
Database paths are reserved for future persistence and are not accessed in this
milestone.

Example (no secrets are required):

```dotenv
HERMES_MODEL_PROVIDER=ollama
HERMES_MODEL=llama3.2
HERMES_OLLAMA_HOST=http://127.0.0.1:11434
HERMES_LOG_LEVEL=INFO
HERMES_MAX_AGENT_ITERATIONS=10
HERMES_TOOL_TIMEOUT_SECONDS=30
HERMES_ALLOWED_FILESYSTEM_ROOTS=data/sandbox
HERMES_BLOCKED_FILESYSTEM_PATTERNS=**/.env;**/.ssh/**;**/*.key;**/*.pem
HERMES_MEMORY_DATABASE=data/memory/hermes.sqlite3
HERMES_RAG_DATABASE=data/rag/hermes.sqlite3
```

## Run

From the project root:

```powershell
python -m app.main --status
python -m app.main --version
python -m app.main --chat
```

Expected status output:

```text
Hermes Local 0.1.0 - running - model: disconnected
```

With `--chat`, the flow is:

`User goal -> AgentController -> ModelProvider -> model decision -> validated calculator request -> calculator -> ToolResult -> ModelProvider -> final response`

Hermes sends each text prompt through the configured provider to Ollama and
prints the normalized response. Only registered tools can be requested, every
request is permission-checked, and failures are returned to the model as
structured results so it can recover. No filesystem, terminal, browser, or
computer-control tools exist at this stage.

## Test

Install the development dependency and run:

```powershell
python -m pip install -r requirements.txt
python -m pytest
```
