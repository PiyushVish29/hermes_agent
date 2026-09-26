# Controlled computer-use boundary

The computer-use flow is:

`Screenshot -> untrusted vision proposal -> structured action -> validation -> PermissionEngine -> backend action -> screenshot -> verification`

The initial tool supports only bounded `click` and `type_text` proposals inside
explicitly configured target bounds. The default target policy is empty and the
default backend is a no-op test backend, so Hermes cannot control the user’s
desktop automatically.

Vision output has no execution authority. Coordinates, target application,
action type, and sensitive permissions are checked before the backend is
called. Screenshots are represented by short-lived metadata and digests in the
result; they are not persisted indefinitely. The backend interface is the
extension point for future computer vision without exposing arbitrary UI
automation commands to the model.