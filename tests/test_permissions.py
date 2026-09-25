"""Permission policy, approval, denial, and audit tests."""

import pytest

from app.security.permissions import (
    AuditEvent,
    PermissionEngine,
    PermissionLevel,
    PermissionPolicy,
    PermissionRequest,
)


def test_safe_policy_allows_and_records_redacted_audit() -> None:
    engine = PermissionEngine(PermissionPolicy({"calculator": PermissionLevel.SAFE}))
    request = PermissionRequest("calculator", "calculator", {"expression": "secret-value"})

    decision = engine.decide(request)

    assert decision.permitted
    assert decision.level is PermissionLevel.SAFE
    event = engine.audit_events[-1]
    assert isinstance(event, AuditEvent)
    assert event.argument_keys == ("expression",)
    assert "secret-value" not in repr(event)


def test_unknown_action_fails_closed() -> None:
    engine = PermissionEngine(PermissionPolicy({"calculator": PermissionLevel.SAFE}))

    decision = engine.decide(PermissionRequest("shell", "shell", {"command": "secret"}))

    assert decision.level is PermissionLevel.BLOCKED
    assert not decision.permitted


def test_approval_required_supports_approve_once_then_expires() -> None:
    engine = PermissionEngine(PermissionPolicy({"network": PermissionLevel.APPROVAL_REQUIRED}))
    request = PermissionRequest("network_call", "network")

    pending = engine.decide(request)
    engine.approve_once(request.request_id)
    approved = engine.decide(request)
    expired = engine.decide(request)

    assert not pending.permitted
    assert approved.permitted
    assert not expired.permitted
    assert expired.reason == "user approval is required"


def test_user_deny_is_authoritative() -> None:
    engine = PermissionEngine(PermissionPolicy({"network": PermissionLevel.APPROVAL_REQUIRED}))
    request = PermissionRequest("network_call", "network")
    engine.deny(request.request_id)

    decision = engine.decide(request)

    assert not decision.permitted
    assert decision.reason == "request was denied by the user"


def test_model_cannot_grant_itself_permission_or_change_policy() -> None:
    engine = PermissionEngine(PermissionPolicy({"network": PermissionLevel.APPROVAL_REQUIRED}))
    model_request = PermissionRequest("network_call", "network", source="llm")

    decision = engine.decide(model_request)

    assert not decision.permitted
    with pytest.raises(TypeError):
        engine.policy.levels["network"] = PermissionLevel.SAFE