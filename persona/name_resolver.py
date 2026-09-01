"""name_resolver.py — User name extraction, persistence & greeting-term resolver.

Single source of truth for:
  * what Musku should call the user in GREETINGS ("dear" by default, or their name)
  * extracting the user's name from phrases like "mujhe X bulao" / "my name is X"
  * persisting that name across sessions (config.json + user_profile.json)

Boss/S2/aap are NEVER treated as a real name — they fall back to "dear".
"""
from __future__ import annotations

import json
import os
import re
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
PROFILE_FILE = os.path.join(BASE_DIR, "musku_data", "user_profile.json")

RESERVED = {"boss", "bosss", "b0ss", "s2", "aap", "none", "user name", "name", "sir", "saheb", "sahab"}
_LOCK = threading.Lock()


def _is_valid_name(name: str | None) -> bool:
    if not name:
        return False
    n = name.strip().lower()
    if not n:
        return False
    if n in RESERVED:
        return False
    # Allow letters, digits, spaces, apostrophes, dots (e.g. "Rahul", "Rahul K.", "J.J")
    if not re.fullmatch(r"[A-Za-z0-9_'. ]{1,30}", n):
        return False
    return True


def load_persisted_name() -> str:
    """Return the saved user name if valid, else '' (per-user aware)."""
    # Multi-tenant: if a uid is active, read that user's own config.
    try:
        from user_context import get_uid
        if get_uid():
            from user_context import load_config
            nm = load_config().get("user_name")
            if _is_valid_name(nm):
                return nm.strip()
            return ""
    except Exception:
        pass
    # 1) config.json is the primary store (used by app.py / live greeting)
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            nm = data.get("user_name")
            if _is_valid_name(nm):
                return nm.strip()
    except Exception:
        pass
    # 2) fallback to user_profile.json
    try:
        if os.path.exists(PROFILE_FILE):
            with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            nm = data.get("user_name")
            if _is_valid_name(nm):
                return nm.strip()
    except Exception:
        pass
    return ""


def resolve_greeting_term() -> str:
    """What to say in a greeting: the user's name if known, else 'dear'."""
    name = load_persisted_name()
    return name if name else "dear"


_NAME_PATTERNS = [
    # mujhe X bulao / mujhe X bulana
    re.compile(r"mujhe\s+([A-Za-z][A-Za-z0-9_'.]*)\s+bula(?:o|na)", re.I),
    # mera naam X hai / mera name X hai / mera naam X rakho
    re.compile(r"mera\s+(?:naam|name)\s+([A-Za-z][A-Za-z0-9_'. ]*?)\s+(?:hai|he|h|is|rakho|rakhna|hoon|hu|hun)\b", re.I),
    # my name is X / my name X
    re.compile(r"my\s+name\s+(?:is\s+)?([A-Za-z][A-Za-z0-9_'. ]*?)(?:\s*$|\s+[.?!])", re.I),
    # call me X
    re.compile(r"call\s+me\s+([A-Za-z][A-Za-z0-9_'. ]*?)(?:\s*$|\s+[.?!])", re.I),
    # name X rakho (generic)
    re.compile(r"\bname\s+([A-Za-z][A-Za-z0-9_'. ]*?)\s+rakho", re.I),
]


def extract_user_name(text: str) -> str | None:
    """Extract a user-provided name from a sentence, else None.

    Handles Hinglish + English: 'mujhe Rahul bulao', 'mera naam Honey hai',
    'my name is Rohit', 'call me Sweetu', etc.
    """
    if not text:
        return None
    t = text.strip()
    for pat in _NAME_PATTERNS:
        m = pat.search(t)
        if m:
            cand = m.group(1).strip().strip(".'\" ")
            # Drop trailing reserved filler words
            cand = re.sub(r"\s+(hai|he|h|is|rakho|rakhna|hoon|hu|hun|ji)\s*$", "", cand, flags=re.I).strip()
            if _is_valid_name(cand):
                return cand
    return None


def save_user_name(name: str) -> bool:
    """Persist the user's name. Per-user aware (uid) else legacy global store."""
    name = (name or "").strip()
    if not _is_valid_name(name):
        return False
    # Multi-tenant: persist into the active user's own config.
    try:
        from user_context import get_uid
        if get_uid():
            from user_context import save_config
            save_config({"user_name": name})
            return True
    except Exception:
        pass
    with _LOCK:
        # config.json — preserve all other (possibly encrypted) fields
        try:
            data = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data["user_name"] = name
            # atomic write to avoid 00-byte corruption on crash
            import tempfile
            dir_name = os.path.dirname(os.path.abspath(CONFIG_FILE)) or "."
            fd, tmp = tempfile.mkstemp(dir=dir_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, CONFIG_FILE)
            finally:
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except Exception:
                    pass
        except Exception:
            pass
        # user_profile.json — best-effort mirror
        try:
            os.makedirs(os.path.dirname(PROFILE_FILE), exist_ok=True)
            pdata = {}
            if os.path.exists(PROFILE_FILE):
                with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                    pdata = json.load(f)
            pdata["user_name"] = name
            with open(PROFILE_FILE, "w", encoding="utf-8") as f:
                json.dump(pdata, f, indent=4, ensure_ascii=False)
        except Exception:
            pass
    return True


def maybe_save_user_name(text: str) -> str | None:
    """If the text reveals the user's name, save it and return the name, else None."""
    nm = extract_user_name(text)
    if nm and save_user_name(nm):
        return nm
    return None
