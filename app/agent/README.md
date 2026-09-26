# Agent emergency stop

`EmergencyStop` is a host-owned thread-safe latch. The host triggers it with
`AgentController.trigger_emergency_stop()`, not through a model tool call.

The controller checks the latch before model generation, before each plan step,
after tool execution, before retries/replans, and before memory-task resume.
Active tools with a `cancel()` hook receive cancellation; pending futures are
cancelled where Python can do so. The active task and plan remain available for
safe shutdown diagnostics.