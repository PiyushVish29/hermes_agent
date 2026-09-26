"""Host-owned emergency stop latch for Hermes tasks."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class EmergencyStopStatus:
    triggered: bool
    reason: str | None = None
    triggered_at: datetime | None = None
    request_count: int = 0


class EmergencyStop:
    """Thread-safe, one-way stop signal until the host creates a new session."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._status = EmergencyStopStatus(False)

    def trigger(self, reason: str = "host emergency stop") -> EmergencyStopStatus:
        """Trigger the stop; repeated calls remain safe and cannot unset it."""
        with self._lock:
            count = self._status.request_count + 1
            if not self._status.triggered:
                self._status = EmergencyStopStatus(True, reason, datetime.now(timezone.utc), count)
                self._event.set()
            else:
                self._status = EmergencyStopStatus(
                    True, self._status.reason, self._status.triggered_at, count
                )
            return self._status

    def is_triggered(self) -> bool:
        return self._event.is_set()

    @property
    def status(self) -> EmergencyStopStatus:
        with self._lock:
            return self._status