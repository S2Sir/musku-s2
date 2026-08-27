"""drift_guard.py — Persona Drift Protection & Injection Defense Guard."""
from __future__ import annotations

from .identity_policy import validate_identity


def validate_compiled_persona(prompt: str) -> bool:
    """Validate compiled system prompt against drift or injection overrides."""
    if not prompt:
        return False
    t = str(prompt)
    if not validate_identity(t):
        return False
    if "=== MUSKU IMMUTABLE IDENTITY LOCK" not in t:
        return False
    if "S2 Sir" not in t:
        return False
    return True
