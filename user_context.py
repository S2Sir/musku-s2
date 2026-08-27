"""user_context.py — Multi-tenant user identity, isolation & per-user config.

Single source of truth for:
  * resolving a user id (anonymous UUID from browser, or legacy "owner")
  * per-user config (api key, language, voice, relationship_mode, user_name)
  * per-user data roots (musku_users/<uid>/...) — see memory/paths.py for paths

Design: an anonymous UUID is generated in the browser (localStorage) and sent on
every request (WS query param + HTTP body/header). The server scopes ALL storage
and the Gemini session to that uid, so user A's chats / persona / memory never
leak to user B. The legacy local user is "owner" and keeps the original global
paths/config (backward compatible).
"""
from __future__ import annotations

import json
import os
import threading

def decrypt_value(v):
    return v.strip() if isinstance(v, str) else v

def encrypt_value(v):
    return v

from tenant_ctx import safe_uid, set_uid, get_uid, is_owner  # single shared tenant ctx

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_ROOT = os.path.join(BASE_DIR, "musku_users")
LEGACY_CONFIG = os.path.join(BASE_DIR, "config.json")

# Safe, deterministic default config for a brand-new web user.
DEFAULT_CONFIG = {
    "user_name": "S2",
    "language": "hinglish",
    "relationship_mode": "best_friend",
    "musku_voice": "Aoede",
    "musku_voice_gain": 1.8,
}

_OWNER = "owner"

# --------------------------------------------------------------------------- #
# runtime persona / relationship_mode switch (Phase 4)
# --------------------------------------------------------------------------- #
# canonical modes -> trigger phrases (command-like to avoid false positives)
PERSONA_KEYWORDS = [
    ("best_friend", [
        "best friend ban", "best friend mode", "bestie mode", "jaise pehle",
        "pehle jaise", "normal mode", "default mode", "waise hi reh",
        "apne jaisa reh", "best friend ki tarah",
    ]),
    ("friend", [
        "dost ban", "dost ki tarah", "dost mode", "friend mode", "casual ban",
        "casual mode", "buddy ban", "bhai ki tarah", "chill mode", "dost bano",
    ]),
    ("formal", [
        "formal ban", "formal mode", "professional ban", "professional mode",
        "respectful ban", "aap jaisa ban", "boss ki tarah", "professional reh",
        "respectful mode",
    ]),
]

PERSONA_SWITCH_REPLY = {
    "best_friend": "Okay dear, waise hi rahungi — tumhari best friend!",
    "friend": "Okay, ab se dost ki tarah baat karungi!",
    "formal": "Okay, ab se thoda formal aur respectful rahungi.",
}


def detect_persona_mode(text) -> str | None:
    """Detect a runtime relationship_mode switch command. Returns mode or None."""
    if not text:
        return None
    t = " ".join(str(text).lower().split())
    for mode, kws in PERSONA_KEYWORDS:
        for kw in kws:
            if kw in t:
                return mode
    return None


def set_relationship_mode(uid, mode: str) -> dict:
    """Persist a per-user relationship_mode; returns saved config."""
    if mode not in PERSONA_SWITCH_REPLY:
        mode = "best_friend"
    return save_config({"relationship_mode": mode}, uid)


def user_dir(uid=None) -> str:
    u = safe_uid(uid if uid is not None else get_uid())
    if u == _OWNER:
        return BASE_DIR
    return os.path.join(USERS_ROOT, u)


def user_config_file(uid=None) -> str:
    return os.path.join(user_dir(uid), "config.json")


# --------------------------------------------------------------------------- #
# per-user config
# --------------------------------------------------------------------------- #
def load_config(uid=None) -> dict:
    """Load per-user config merged with defaults/legacy.

    owner -> reads global config.json (legacy). New web user -> reads their
    own config.json (created on first save), merged over DEFAULT_CONFIG.
    """
    u = safe_uid(uid if uid is not None else get_uid())
    if u == _OWNER:
        cfg = _read_json(LEGACY_CONFIG) or {}
        if cfg.get("gemini_api_key"):
            cfg["gemini_api_key"] = decrypt_value(cfg["gemini_api_key"])
        merged = dict(DEFAULT_CONFIG)
        merged.update(cfg)
        return merged

    f = user_config_file(u)
    if os.path.exists(f):
        cfg = _read_json(f) or {}
        if cfg.get("gemini_api_key"):
            cfg["gemini_api_key"] = decrypt_value(cfg["gemini_api_key"])
        merged = dict(DEFAULT_CONFIG)
        merged.update(cfg)
        return merged
    # brand-new user: inherit safe defaults (no key yet)
    return dict(DEFAULT_CONFIG)


def save_config(patch: dict, uid=None) -> dict:
    """Persist a per-user config patch (merges). Returns the saved config."""
    u = safe_uid(uid if uid is not None else get_uid())
    if u == _OWNER:
        path = LEGACY_CONFIG
    else:
        os.makedirs(user_dir(u), exist_ok=True)
        path = user_config_file(u)

    data = _read_json(path) or {}
    data.update(patch)
    if data.get("gemini_api_key"):
        data["gemini_api_key"] = encrypt_value(data["gemini_api_key"])
    _write_json(path, data)
    out = dict(data)
    if out.get("gemini_api_key"):
        out["gemini_api_key"] = decrypt_value(out["gemini_api_key"])
    return out


def ensure_user_dir(uid) -> str:
    """Create the per-user directory tree if missing; returns data dir."""
    d = user_dir(uid)
    os.makedirs(os.path.join(d, "musku_data"), exist_ok=True)
    os.makedirs(os.path.join(d, "musku_chat"), exist_ok=True)
    return d


# --------------------------------------------------------------------------- #
# request helpers (browser -> server)
# --------------------------------------------------------------------------- #
def extract_uid_from_query(query_string: str):
    """Parse ?uid=... from a WS/HTTP query string."""
    if not query_string:
        return None
    for pair in query_string.split("&"):
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        if k.strip() == "uid":
            v = v.strip()
            return v or None
    return None


def extract_uid_from_headers(headers: dict):
    """Read X-Musku-Uid header (case-insensitive)."""
    if not headers:
        return None
    low = {str(k).lower(): v for k, v in headers.items()}
    return (low.get("x-musku-uid") or "").strip() or None


# --------------------------------------------------------------------------- #
# internal json io
# --------------------------------------------------------------------------- #
def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[UserConfig Write Error]: {e}")
