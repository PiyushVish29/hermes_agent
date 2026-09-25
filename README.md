# Hermes Local

Hermes Local is a privacy-first, Windows-focused AI computer agent. This repository contains milestone 1: a safe Python application shell that starts, reports its status, and shuts down cleanly.

## Milestone boundary

The application does **not** connect to an LLM, execute arbitrary code, access files, control the computer, browse the web, persist memory, or perform retrieval. The interfaces for future capabilities are present only to establish clean ownership boundaries.

## Architecture

- `app/main.py`: CLI entry point and process lifecycle wiring.
- `app/agent/`: application orchestration. `AgentController` owns start/status/shutdown state.
- `app/models/`: model-provider contract. Future local or hosted adapters implement `ModelProvider`; the controller does not depend on a vendor SDK.
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

## Security boundaries

The model must never become the security boundary. Future model output will be treated as untrusted intent. The agent layer will request named tools, the registry will expose only approved tools, and the permission engine will make explicit policy decisions before execution. No unrestricted filesystem, shell, Python, PowerShell, CMD, browser, or desktop-control capability exists in this milestone.

## Run

From the project root:

```powershell
python -m app.main --status
python -m app.main --version
```

Expected status output:

```text
Hermes Local 0.1.0 - running - model: disconnected
```

## Test

Install the development dependency and run:

```powershell
python -m pip install -r requirements.txt
python -m pytest
```
