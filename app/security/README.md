# Security boundary

`PermissionEngine` owns policy decisions independently from model output and
tool implementations. Every tool declares a permission requirement, and every
request is represented by `PermissionRequest` before execution.

`PermissionPolicy` supports `SAFE`, `APPROVAL_REQUIRED`, and `BLOCKED`. Unknown
requirements fail closed. One-time approvals and denials are host-side engine
operations; the model receives only the resulting decision and cannot change
policy. `AuditEvent` records action, outcome, and argument names, never argument
values or secrets.

Tools do not receive the registry or permission engine as execution arguments.
A tool must not invoke another tool internally; a separate model request must
go through the same registry and permission path. This leaves room for future
task/session approvals, sandbox policies, and sensitive-data policies without
changing the agent contract.

Filesystem roots, blocked patterns, and the maximum readable file size are
configured outside the model through `SecurityPolicy` and environment-backed
application settings.
