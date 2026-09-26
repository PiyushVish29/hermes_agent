"""Narrow backend seam for controlled test environments and future vision support."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.computer.models import ComputerAction, Screenshot, VisionProposal


class ComputerBackend(ABC):
    """Backend receives validated actions only, never raw vision output."""

    @abstractmethod
    def screenshot(self, target_application: str) -> Screenshot:
        raise NotImplementedError

    @abstractmethod
    def perform(self, proposal: VisionProposal, timeout_seconds: float) -> None:
        raise NotImplementedError

    @abstractmethod
    def verify(self, before: Screenshot, proposal: VisionProposal, after: Screenshot) -> bool:
        raise NotImplementedError

    def cancel(self) -> None:
        """Optional backend cancellation hook for emergency stop integration."""


class ControlledTestBackend(ComputerBackend):
    """No-op backend intended for local tests, never connected to the desktop."""

    def __init__(self, bounds) -> None:
        self.bounds = bounds
        self.actions: list[VisionProposal] = []
        self._version = 0

    def screenshot(self, target_application: str) -> Screenshot:
        import hashlib
        import time

        digest = hashlib.sha256(f"{target_application}:{self._version}".encode()).hexdigest()
        return Screenshot(target_application, self.bounds, digest, time.time())

    def perform(self, proposal: VisionProposal, timeout_seconds: float) -> None:
        self.actions.append(proposal)
        self._version += 1

    def verify(self, before: Screenshot, proposal: VisionProposal, after: Screenshot) -> bool:
        return before.target_application == after.target_application and before.digest != after.digest