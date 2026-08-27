"""tenant_ctx.py — Single shared user-tenant context (contextvar).

Both `user_context` and `memory.paths` (and the live/chat layers) resolve the
active user id from THIS one contextvar, so setting the uid once per
request/session scopes config + storage everywhere consistently.
"""
from __future__ import annotations

import contextvars
import re

_UID_CTX = contextvars.ContextVar("musku_uid", default=None)


def safe_uid(uid) -> str:
    """Filesystem-safe tenant token (no path traversal)."""
    if not uid:
        return "owner"
    s = str(uid).strip()
    # reject anything that could escape the users root
    if "/" in s or "\\" in s or ".." in s:
        return "owner"
    s = re.sub(r"[^A-Za-z0-9_-]", "", s)
    return s[:64] or "owner"


def set_uid(uid) -> None:
    s = safe_uid(uid)
    _UID_CTX.set(None if s == "owner" else s)


def get_uid():
    u = _UID_CTX.get()
    return None if u == "owner" else u


def is_owner(uid=None) -> bool:
    u = safe_uid(uid if uid is not None else _UID_CTX.get())
    return u == "owner"
