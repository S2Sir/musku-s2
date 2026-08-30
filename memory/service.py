"""memory/service.py — MemoryService (Single Writer for Firebase Memory)

PRO Architecture: All memory operations go through this service.
- Verified UID only (from TenantContext)
- Firestore is Truth, Local JSON is cache/fallback
- Smart extraction threshold + UPDATE/MERGE/REMOVE supported
"""
from __future__ import annotations

import re
from typing import Optional

from tenant_ctx import get_uid, safe_uid


# Thresholds for smart extraction
IMPORTANCE_THRESHOLD = 0.6
CONFIDENCE_THRESHOLD = 0.6
MIN_FACT_LENGTH = 8


def _verified_uid(uid: str | None = None) -> str | None:
    """Return verified UID from TenantContext if not explicitly passed."""
    if uid is not None:
        return safe_uid(uid)
    u = get_uid()
    return safe_uid(u) if u else None


def get_memory(uid: str | None = None, category: str | None = None):
    """Load memory via MemoryService (tenant-scoped)."""
    from memory.store import load_file, load_all
    from memory import paths
    # Paths already respect TenantContext, so no manual uid needed for local
    if category:
        file = paths.MEMORY_FILE_MAP.get(category)
        key = paths.MEMORY_KEY_NAMES.get(category, "items")
        if file and key:
            return load_file(file, key)
        return []
    return load_all()


def save_memory(category: str, fact: str, source: str = "", importance: float = 0.5, confidence: float = 0.7, uid: str | None = None) -> bool:
    """Single writer for memory creation. Enforces threshold."""
    if not fact or len(fact.strip()) < MIN_FACT_LENGTH:
        return False
    if importance < IMPORTANCE_THRESHOLD and confidence < CONFIDENCE_THRESHOLD:
        # Low value fact - don't persist to Firebase
        return False
    _uid = _verified_uid(uid)
    if _uid:
        from tenant_ctx import set_uid
        set_uid(_uid)
    from memory.store import save_memory as _save
    return _save(category, fact, source=source, importance=importance)


def update_memory(mem_id: str | None = None, fact: str | None = None, category: str | None = None, new_fact: str | None = None, uid: str | None = None) -> bool:
    _uid = _verified_uid(uid)
    if _uid:
        from tenant_ctx import set_uid
        set_uid(_uid)
    from memory.store import update_memory_entry
    return update_memory_entry(mem_id=mem_id, fact=fact, category=category, new_fact=new_fact)


def merge_memory(category: str, facts: list, uid: str | None = None) -> bool:
    """Merge multiple facts into category (deduped)."""
    _uid = _verified_uid(uid)
    if _uid:
        from tenant_ctx import set_uid
        set_uid(_uid)
    from memory.store import save_memory as _save
    ok = False
    for f in facts or []:
        if _save(category, f, source="merge"):
            ok = True
    return ok


def delete_memory(mem_id: str | None = None, fact: str | None = None, uid: str | None = None) -> bool:
    _uid = _verified_uid(uid)
    if _uid:
        from tenant_ctx import set_uid
        set_uid(_uid)
    from memory.store import remove_memory_entry
    return remove_memory_entry(mem_id=mem_id, fact=fact)


def search_relevant_memory(query: str, uid: str | None = None, max_per_cat: int = 3):
    """Load memory relevant to query (keyword-routed)."""
    _uid = _verified_uid(uid)
    if _uid:
        from tenant_ctx import set_uid
        set_uid(_uid)
    from memory.store import load_routed
    return load_routed(query)
