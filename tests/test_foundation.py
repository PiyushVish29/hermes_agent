"""Smoke tests for the milestone foundation."""

from app.agent.controller import AgentController
from app.config.settings import Settings
from app.security.permissions import PermissionEngine
from app.tools.registry import ToolRegistry


def test_controller_reports_safe_lifecycle() -> None:
    controller = AgentController(Settings())
    controller.start()
    assert "running" in controller.status_message()
    assert "model: disconnected" in controller.status_message()
    controller.shutdown()
    assert "stopped" in controller.status_message()


def test_registry_starts_empty() -> None:
    assert ToolRegistry().names() == ()


def test_permissions_deny_by_default() -> None:
    assert not PermissionEngine().is_allowed("anything", {})
