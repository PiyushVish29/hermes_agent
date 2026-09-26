# Hermes Local

Hermes Local is a privacy-first, Windows-focused AI computer agent. This repository contains milestone 1: a safe Python application shell that starts, reports its status, and shuts down cleanly.

## Milestone boundary

The application does **not** execute arbitrary code, provide unrestricted computer control, browse the web, persist memory, or perform retrieval. It includes bounded read-only filesystem tools, controlled browser actions, and explicit application lifecycle operations only.

## Architecture

- `app/main.py`: CLI entry point and process lifecycle wiring.
- `app/agent/`: application orchestration. `AgentController` owns start/status/shutdown state.
- `app/models/`: provider-neutral model contracts, factory, and mock adapter. Future local or hosted adapters implement `ModelProvider`; the controller does not depend on a vendor SDK.
- `app/tools/`: explicit tool contracts and `ToolRegistry`. Tools must be registered before they can be considered by future orchestration.
- `app/filesystem/`: path security and read-only filesystem tools. Access is limited to configured roots, blocked sensitive paths, and a file-size limit.
- `app/terminal/`: fixed-catalog, non-shell Windows development commands with timeout, cancellation, and output limits.
- `app/browser/`: isolated, allowlisted browser actions with visible-text extraction and no arbitrary scripting.
- `app/applications/`: explicit Windows application catalog with launch, status, focus, and approval-gated close operations.
- `app/computer/`: controlled test-target computer-use actions with screenshot verification; no desktop-wide control.
- `app/sandbox/`: explicit resettable sandbox-scoped filesystem and terminal facades.
- `app/security/`: policy boundary. `PermissionEngine` currently denies all requests by default.
- `app/memory/`: short-term session context and approval-gated SQLite long-term memory.
- `app/rag/`: separate approved-document indexing, local embeddings, chunk retrieval, and source references.
- `app/rag/`: future retrieval boundary over approved local indexes.
- `app/config/`: typed, allowlisted environment configuration.
- `app/utils/`: shared infrastructure such as logging.
- `data/`: reserved local runtime areas for memory, RAG indexes, logs, and sandbox data.
- `tests/`: smoke tests for the foundation.

## Planning loop

Agent work follows:

`Goal -> Plan -> Execute -> Observe -> Verify -> Continue or Replan`

Each `PlanStep` records its objective, registered tool, arguments, expected
result, actual structured result, status, and attempts. Successful steps remain
in `plan_history`; only failed steps are retried. Once the configured retry
limit is reached, Hermes asks the model for a revised plan subject to the
configured replan limit. Every recovery tool request goes through the same
validation and PermissionEngine path. Memory approval pauses preserve the exact
task checkpoint before execution resumes.

## Emergency stop

The host/UI calls `AgentController.trigger_emergency_stop()` to latch an
independent stop signal. This mechanism is not exposed to the model and cannot
be disabled by an LLM request. It prevents new model turns, tools, retries,
replans, and memory-resume execution; active tools receive their `cancel()`
hook, pending futures are cancelled where possible, and the controller keeps
the active task, plan history, and event state for safe shutdown inspection.

The stop is one-way for the current controller session; create a new host
session to clear it. An already-running OS process, HTTP request, or provider
call may not be safely interruptible by Python. Hermes requests cooperative
cancellation, terminates only operations with a safe cancel path, and otherwise
waits for the underlying operation to return while refusing subsequent work.

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

The model must never become the security boundary. Future model output will be treated as untrusted intent. The agent layer will request named tools, the registry will expose only approved tools, and the permission engine will make explicit policy decisions before execution. No unrestricted filesystem, write, delete, shell, Python, PowerShell, CMD, arbitrary browser scripting, or desktop-wide mouse/keyboard automation exists in this milestone. Filesystem access is always resolved and permission-checked before I/O; terminal, application, and computer-use operations come only from fixed or explicitly configured boundaries.

Sandbox mode is explicit and visibly labeled `SANDBOX MODE`; it never silently
redirects normal operations. The sandbox root is `data/sandbox/` and can be
reset without touching real user directories.

## Configuration

Copy `.env.example` to `.env` and export those values before starting Hermes.
`HERMES_ALLOWED_FILESYSTEM_ROOTS` is required; Hermes fails closed when that
security setting is missing or unsafe. Roots are separated with `;` on Windows.
The default root is only `data/sandbox`, never the user's entire filesystem.
The memory database is used for approved long-term memories; the RAG database
path remains reserved for future retrieval persistence.

Example (no secrets are required):

```dotenv
HERMES_MODEL_PROVIDER=ollama
HERMES_MODEL=llama3.2
HERMES_OLLAMA_HOST=http://127.0.0.1:11434
HERMES_LOG_LEVEL=INFO
HERMES_MAX_AGENT_ITERATIONS=10
HERMES_MAX_STEP_RETRIES=2
HERMES_MAX_REPLANS=3
HERMES_TOOL_TIMEOUT_SECONDS=30
HERMES_TERMINAL_OUTPUT_LIMIT_BYTES=65536
HERMES_BROWSER_ALLOWED_HOSTS=
HERMES_BROWSER_SEARCH_URL=
HERMES_BROWSER_MAX_RESPONSE_BYTES=1048576
HERMES_BROWSER_TIMEOUT_SECONDS=15
HERMES_ALLOWED_FILESYSTEM_ROOTS=data/sandbox
HERMES_BLOCKED_FILESYSTEM_PATTERNS=**/.env;**/.ssh/**;**/*.key;**/*.pem
HERMES_MAX_FILESYSTEM_FILE_SIZE_BYTES=1048576
HERMES_MEMORY_DATABASE=data/memory/hermes.sqlite3
HERMES_RAG_DATABASE=data/rag/hermes.sqlite3
# Optional: leave empty to disable indexing until roots are explicitly selected.
HERMES_RAG_INDEX_ROOTS=
HERMES_RAG_FILE_EXTENSIONS=.txt,.md,.rst,.py,.json,.yaml,.yml
HERMES_RAG_CHUNK_SIZE_CHARS=1200
HERMES_RAG_CHUNK_OVERLAP_CHARS=200
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
structured results so it can recover. The terminal tool exposes only
explicitly catalogued harmless development commands and never invokes a shell.

## Test

Install the development dependency and run:

```powershell
python -m pip install -r requirements.txt
python -m pytest
```
