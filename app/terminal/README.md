# Controlled terminal boundary

`TerminalTool` accepts a command name, not a shell string. The host supplies a
fixed `CommandPolicy` whose `CommandSpec` entries classify commands as
`ALLOWED`, `APPROVAL_REQUIRED`, or `BLOCKED`. Unknown names and user-supplied
arguments are rejected unless a catalog entry explicitly permits them.

Execution uses `subprocess.Popen` with `shell=False`, a sanitized environment,
separate stdout/stderr capture, a timeout, bounded output, and host-side
cancellation. The model cannot register commands, modify policy, construct
PowerShell/CMD scripts, or access credentials.