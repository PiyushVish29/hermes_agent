"""Memory usefulness and sensitivity policy."""

from __future__ import annotations

import re

from app.memory.models import MemoryCategory, SensitivityResult


class MemoryPolicy:
    """Decide whether a candidate may enter the approval workflow."""

    _sensitive_patterns = (
        (re.compile(r"\b(password|passwd|passphrase)\b", re.IGNORECASE), "credential"),
        (re.compile(r"\b(api[_ -]?key|access[_ -]?token|refresh[_ -]?token)\b", re.IGNORECASE), "credential"),
        (re.compile(r"\b(private[_ -]?key|secret|session[_ -]?cookie|browser credential)\b", re.IGNORECASE), "credential"),
        (re.compile(r"\b(credit card|bank account|financial credential)\b", re.IGNORECASE), "financial credential"),
    )

    def assess(self, category: MemoryCategory, content: str) -> SensitivityResult:
        if category is MemoryCategory.SENSITIVE_INFORMATION:
            return SensitivityResult(True, "sensitive information category is never persisted")
        for pattern, reason in self._sensitive_patterns:
            if pattern.search(content):
                return SensitivityResult(True, f"possible {reason} detected")
        return SensitivityResult(False)

    def can_persist_without_approval(self, candidate_category: MemoryCategory, explicit: bool) -> bool:
        return explicit and candidate_category not in {
            MemoryCategory.CURRENT_TASK,
            MemoryCategory.TEMPORARY_CONTEXT,
        }