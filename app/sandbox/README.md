# Hermes sandbox

`SandboxManager` is explicit and opt-in. It owns `data/sandbox/`, reports
`SANDBOX MODE`, and provides sandbox-scoped filesystem and terminal facades.
Normal Hermes tools are never redirected into this root.

Sandbox filesystem paths are resolved against the sandbox root and retain the
same traversal, symlink, sensitive-file, and permission checks as normal
filesystem access. Sandbox terminal commands use the sandbox as their working
directory but still use the fixed non-shell command catalog. `reset()` removes
only children contained by the sandbox root.