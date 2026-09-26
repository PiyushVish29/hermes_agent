"""Windows application backend with no general UI automation surface."""

from __future__ import annotations

import csv
import ctypes
import io
import os
import subprocess
from abc import ABC, abstractmethod

from app.applications.models import ApplicationSpec


class ApplicationBackend(ABC):
    """Narrow backend seam for future computer-vision interaction."""

    @abstractmethod
    def launch(self, spec: ApplicationSpec) -> tuple[bool, tuple[int, ...]]:
        raise NotImplementedError

    @abstractmethod
    def status(self, spec: ApplicationSpec, timeout_seconds: float) -> tuple[bool, tuple[int, ...]]:
        raise NotImplementedError

    @abstractmethod
    def focus(self, spec: ApplicationSpec, timeout_seconds: float) -> tuple[bool, tuple[int, ...]]:
        raise NotImplementedError

    @abstractmethod
    def close(self, spec: ApplicationSpec, timeout_seconds: float) -> tuple[bool, tuple[int, ...]]:
        raise NotImplementedError


class WindowsApplicationBackend(ApplicationBackend):
    """Use fixed process/window operations, never arbitrary UI automation."""

    def launch(self, spec: ApplicationSpec) -> tuple[bool, tuple[int, ...]]:
        process = subprocess.Popen(
            [spec.executable, *spec.launch_arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True, (process.pid,)

    def status(self, spec: ApplicationSpec, timeout_seconds: float) -> tuple[bool, tuple[int, ...]]:
        process_ids = self._process_ids(spec, timeout_seconds)
        return bool(process_ids), process_ids

    def focus(self, spec: ApplicationSpec, timeout_seconds: float) -> tuple[bool, tuple[int, ...]]:
        process_ids = self._process_ids(spec, timeout_seconds)
        if not process_ids or os.name != "nt":
            return False, process_ids
        focused = self._window_action(process_ids[0], close=False)
        return focused, process_ids

    def close(self, spec: ApplicationSpec, timeout_seconds: float) -> tuple[bool, tuple[int, ...]]:
        process_ids = self._process_ids(spec, timeout_seconds)
        if not process_ids or os.name != "nt":
            return False, process_ids
        closed = self._window_action(process_ids[0], close=True)
        return closed, process_ids

    @staticmethod
    def _process_ids(spec: ApplicationSpec, timeout_seconds: float) -> tuple[int, ...]:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        names = {name.lower() for name in spec.process_names}
        process_ids = []
        for row in csv.reader(io.StringIO(result.stdout)):
            if len(row) >= 2 and row[0].strip('"').lower() in names:
                try:
                    process_ids.append(int(row[1].strip('"')))
                except ValueError:
                    continue
        return tuple(process_ids)

    @staticmethod
    def _window_action(process_id: int, *, close: bool) -> bool:
        user32 = ctypes.windll.user32
        result = False
        wm_close = 0x0010

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def callback(hwnd, _lparam):
            nonlocal result
            owner = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == process_id and user32.IsWindowVisible(hwnd):
                result = bool(user32.PostMessageW(hwnd, wm_close, 0, 0)) if close else bool(user32.SetForegroundWindow(hwnd))
                return False
            return True

        user32.EnumWindows(callback, 0)
        return result