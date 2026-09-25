"""External security policy and authorization decisions for tool requests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class PermissionLevel(str, Enum):
    SAFE = "safe"
    APPROVAL_REQUIRED = "approval_required"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class PermissionPolicy:
    """Immutable action policy configured by the host, never by the model."""

    levels: Mapping[str, PermissionLevel] = field(default_factory=dict)
    default_level: PermissionLevel = PermissionLevel.BLOCKED

    def __post_init__(self) -> None:
        normalized = {
            name: level if isinstance(level, PermissionLevel) else PermissionLevel(level)
            for name, level in self.levels.items()
            if name.strip()
        }
        object.__setattr__(self, "levels", MappingProxyType(normalized))

    def level_for(self, requirement: str) -> PermissionLevel:
        """Return the configured level, failing closed for unknown requirements."""
        return self.levels.get(requirement, self.default_level)


@dataclass(frozen=True)
class PermissionRequest:
    """A capability request submitted for external authorization."""

    action: str
    permission_requirement: str
    arguments: Mapping[str, object] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    source: str = "llm"


@dataclass(frozen=True)
class SecurityDecision:
    """The engine's authoritative result for one request."""

    request_id: str
    action: str
    level: PermissionLevel
    permitted: bool
    reason: str


@dataclass(frozen=True)
class AuditEvent:
    """Non-sensitive security audit record; argument values are never stored."""

    request_id: str
    action: str
    level: PermissionLevel
    permitted: bool
    reason: str
    argument_keys: tuple[str, ...]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class PermissionEngine:
    """Authorize every tool request using host policy and host-owned approvals."""

    def __init__(self, policy: PermissionPolicy | frozenset[str] | None = None) -> None:
        if isinstance(policy, frozenset):
            policy = PermissionPolicy({name: PermissionLevel.SAFE for name in policy})
        self._policy = policy or PermissionPolicy()
        self._approved_once: set[str] = set()
        self._denied: set[str] = set()
        self._audit_events: list[AuditEvent] = []

    @property
    def policy(self) -> PermissionPolicy:
        """Expose the immutable policy for inspection, not mutation."""
        return self._policy

    @property
    def audit_events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._audit_events)

    def decide(self, request: PermissionRequest) -> SecurityDecision:
        """Make an authoritative decision and append a redacted audit event."""
        level = self._policy.level_for(request.permission_requirement)
        if level is PermissionLevel.BLOCKED:
            decision = self._decision(request, level, False, "action is blocked by policy")
        elif request.request_id in self._denied:
            decision = self._decision(request, level, False, "request was denied by the user")
        elif level is PermissionLevel.SAFE:
            decision = self._decision(request, level, True, "action is safe by policy")
        elif request.request_id in self._approved_once:
            self._approved_once.remove(request.request_id)
            decision = self._decision(request, level, True, "approved once by the user")
        else:
            decision = self._decision(request, level, False, "user approval is required")
        self._audit_events.append(
            AuditEvent(
                request_id=request.request_id,
                action=request.action,
                level=decision.level,
                permitted=decision.permitted,
                reason=decision.reason,
                argument_keys=tuple(sorted(request.arguments)),
            )
        )
        return decision

    def approve_once(self, request_id: str) -> None:
        """Record one host/user approval; the model cannot call this method."""
        self._denied.discard(request_id)
        self._approved_once.add(request_id)

    def deny(self, request_id: str) -> None:
        """Record a host/user denial for this request."""
        self._approved_once.discard(request_id)
        self._denied.add(request_id)

    def is_allowed(
        self,
        tool_name: str,
        arguments: dict[str, object],
        permission_requirement: str | None = None,
    ) -> bool:
        """Compatibility wrapper that still routes through the full engine."""
        request = PermissionRequest(tool_name, permission_requirement or tool_name, arguments)
        return self.decide(request).permitted

    @staticmethod
    def _decision(
        request: PermissionRequest,
        level: PermissionLevel,
        permitted: bool,
        reason: str,
    ) -> SecurityDecision:
        return SecurityDecision(request.request_id, request.action, level, permitted, reason)