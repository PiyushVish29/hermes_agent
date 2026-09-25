# Memory boundary

Hermes separates current task context from persistent memory.

- `short_term.py` holds conversation, task, plan, observations, and tool
	results for the current session only.
- `policy.py` detects credentials and other sensitive information. Sensitive
	candidates are rejected without asking the user.
- `storage.py` owns SQLite persistence mechanics.
- `long_term.py` applies approval and sensitivity rules around storage.
- `manager.py` coordinates proposals, approval, rejection, CRUD, and exact
	agent task checkpoints.

Non-explicit potentially useful memories remain pending until the host obtains
user approval. Explicit user-directed memories may persist immediately after
sensitivity validation. The model can suggest a candidate but cannot approve,
reject, or alter policy. When approval interrupts an active task,
`MemoryTaskCheckpoint` preserves the task ID, goal, iteration, conversation,
plan, and state so `AgentController.resume_memory_task()` continues the same
task rather than restarting it.
