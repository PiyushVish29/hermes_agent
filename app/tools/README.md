Tools are explicit capabilities registered in `ToolRegistry`. The agent may
only execute a registered tool after permission validation and within the
configured timeout. The first loop exposes only the bounded `calculator` tool;
there is no filesystem, terminal, browser, or arbitrary Python execution.

Each tool supplies a stable name, model-safe description, input schema,
permission requirement, validation hook, and execution method. The registry
rejects unknown names, duplicate registrations, and invalid arguments before
the controller can execute anything. Future filesystem, shell, desktop, or
browser capabilities must be added as narrow registered tools without changing
`AgentController`.
