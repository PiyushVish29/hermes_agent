# Controlled application boundary

`ApplicationTool` exposes only named operations for applications in the
host-owned `ApplicationPolicy`: launch, status, focus, and close. The initial
catalog contains harmless fixed specifications for Notepad and Calculator.

Launch, status, and focus use fixed executable/process metadata. Close uses a
separate `application.close` permission and does not terminate arbitrary
processes. No mouse, keyboard, window-handle, PowerShell, CMD, script, or
computer-vision operation is exposed. `ApplicationBackend` is the narrow seam
where future vision support can be added without changing the tool contract or
agent.