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

try:
    from crypto_utils import decrypt_value as _decrypt, encrypt_value as _encrypt
    def decrypt_value(v):
        return _decrypt(v) if isinstance(v, str) else v
    def encrypt_value(v):
        return _encrypt(v) if isinstance(v, str) else v
except Exception:
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
# runtime persona / relationship_mode switch (Phase 4) — per-user flexible
# --------------------------------------------------------------------------- #
# Unified with persona/relationship_engine aliases: jo bhi user bole (dost/bestie/yaar/jigri/gf/partner/life partner/beti/caring) wahi ban jao
# Boss is NOT a mode — Boss word is purged, only aap/custom name
PERSONA_KEYWORDS = [
    ("best_friend", [
        "best friend ban", "best friend mode", "bestie mode", "bestie ban", "bff ban", "dost ban", "dost bano",
        "dost ki tarah", "dost mode", "best friend ki tarah", "jaise pehle", "pehle jaise", "normal mode", "default mode", "waise hi reh", "apne jaisa reh",
    ]),
    ("jigri", [
        "jigri ban", "jigri dost ban", "yaar ban", "yarr ban", "yaar ki tarah", "jigri ki tarah", "jigri mode", "yaar mode", "buddy ban",
    ]),
    ("beti", [
        "beti ban", "beti ki tarah", "beti mode", "daughter ban", "bachi ban",
    ]),
    ("caring", [
        "caring ban", "caring companion ban", "companion ban", "caring mode", "supporter ban",
    ]),
    ("girlfriend", [
        "girlfriend ban", "gf ban", "partner ban", "life partner ban", "life-partner ban", "soulmate ban", "jaan ban", "premi ban",
        "girlfriend ki tarah", "partner ki tarah", "life partner ki tarah", "soulmate ki tarah",
    ]),
    # generic fallback — "meri X ban jao" will be caught by alias engine too
]

PERSONA_SWITCH_REPLY = {
    "best_friend": "Okay dear, waise hi rahungi — tumhari best friend! 🥰",
    "jigri": "Okay yaar, ab se bilkul jigri dost ki tarah — chulbul masti me! 😊",
    "beti": "Okay, ab se pyaari beti ki tarah — cute aur caring! 🌸",
    "caring": "Okay, ab se tumhari caring companion ki tarah — pyaar se khayal rakhungi! 💖",
    "girlfriend": "Okay, ab se tumhari pyaari girlfriend/partner ki tarah — thodi flirty, bahut pyaari! 🥰",
    # legacy aliases
    "friend": "Okay, ab se dost ki tarah baat karungi!",
    "formal": "Okay, ab se thoda formal aur respectful rahungi.",
}


def detect_persona_mode(text) -> str | None:
    """Detect a runtime relationship_mode switch command. Returns mode or None."""
    if not text:
        return None
    t = " ".join(str(text).lower().split())
    # 1) direct PERSONA_KEYWORDS match (highest priority — explicit "X ban" commands)
    for mode, kws in PERSONA_KEYWORDS:
        for kw in kws:
            if kw in t:
                return mode
    # 2) fallback to relationship_engine alias engine (covers dost/yaar/bestie/gf/partner etc + custom)
    try:
        from persona.relationship_engine import get_relationship_profile
        # try to extract "meri X ban" pattern — let alias engine decide
        import re
        # find "meri <phrase> ban" or "<phrase> ban jao/ban" — use last match
        m = re.search(r"meri\s+([a-zA-Z\u0900-\u097F\s_-]{2,30})\s+ban", t)
        if m:
            cand = m.group(1).strip()
            prof = get_relationship_profile(cand)
            # if custom, prof["id"] will be cand itself (len>=2) — allow custom per-user
            if prof and prof.get("id"):
                pid = prof["id"]
                # Boss is purged — map boss to best_friend/aap
                if pid.lower() in ("boss","bosss","b0ss","s2"):
                    return "best_friend"
                return pid
        # also direct contains check via alias keys (e.g. text contains "bestie" even without "ban")
        for cand in ["best friend","bestie","bff","dost","jigri","yaar","beti","caring","girlfriend","gf","partner","life partner","soulmate","jaan"]:
            if cand in t and ("ban" in t or "bano" in t or "ban jao" in t or "banna" in t or "ki tarah" in t):
                prof = get_relationship_profile(cand)
                return prof["id"]
        # ultra generic: "... ban jao" with any word 2-20 chars — treat as custom
        mg = re.search(r"\b([a-z]{2,20})\s+ban\s*(jao|ja|banao)?\b", t)
        if mg:
            cand2 = mg.group(1).strip()
            if cand2 not in ("boss","bosss","b0ss"):
                prof2 = get_relationship_profile(cand2)
                return prof2["id"]
    except Exception:
        pass
    return None


def set_relationship_mode(uid, mode: str) -> dict:
    """Persist a per-user relationship_mode; returns saved config."""
    # allow any engine mode + custom (len>=2), not just PERSONA_SWITCH_REPLY keys
    try:
        from persona.relationship_engine import get_relationship_profile
        prof = get_relationship_profile(mode)
        # if engine returns a valid profile, persist that id
        if prof and prof.get("id"):
            mid = prof["id"]
            if mid.lower() in ("boss","bosss","b0ss"):
                mid = "best_friend"
            return save_config({"relationship_mode": mid}, uid)
    except Exception:
        pass
    if mode not in PERSONA_SWITCH_REPLY:
        # fallback: if unknown but len>=2 treat as custom
        if isinstance(mode, str) and len(mode.strip()) >= 2 and mode.strip().lower() not in ("boss","bosss","b0ss"):
            return save_config({"relationship_mode": mode.strip().lower()}, uid)
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
    """Load per-user config merged with defaults/legacy + Firestore (100+ BYOK).

    Priority: Firestore encrypted key -> file -> DEFAULT.
    Firestore gives cross-domain + redeploy persistence; file is fallback.
    """
    u = safe_uid(uid if uid is not None else get_uid())
    if u == _OWNER:
        cfg = _read_json(LEGACY_CONFIG) or {}
        if cfg.get("gemini_api_key"):
            cfg["gemini_api_key"] = decrypt_value(cfg["gemini_api_key"])
        merged = dict(DEFAULT_CONFIG)
        merged.update(cfg)
        return merged

    # Try Firestore first (cross-domain, survives redeploy)
    fs_enc = None
    try:
        from firebase.api_keys import load_api_key_fs
        fs_enc = load_api_key_fs(u)
    except Exception:
        fs_enc = None

    f = user_config_file(u)
    if os.path.exists(f):
        cfg = _read_json(f) or {}
        # Firestore wins if present
        if fs_enc:
            cfg["gemini_api_key"] = fs_enc
        if cfg.get("gemini_api_key"):
            cfg["gemini_api_key"] = decrypt_value(cfg["gemini_api_key"])
        merged = dict(DEFAULT_CONFIG)
        merged.update(cfg)
        # Opportunistic migrate: Firestore empty but file has key -> push to FS
        if not fs_enc and cfg.get("gemini_api_key"):
            try:
                from firebase.api_keys import save_api_key_fs
                from crypto_utils import encrypt_value as _enc2
                hint = cfg["gemini_api_key"][:6] + "..." + cfg["gemini_api_key"][-4:] if len(cfg["gemini_api_key"]) > 10 else ""
                save_api_key_fs(u, _enc2(cfg["gemini_api_key"]), hint)
            except Exception:
                pass
        return merged

    if fs_enc:
        try:
            dec = decrypt_value(fs_enc)
            merged = dict(DEFAULT_CONFIG)
            merged["gemini_api_key"] = dec
            # materialize file for offline fallback
            try:
                os.makedirs(user_dir(u), exist_ok=True)
                _write_json(f, {"gemini_api_key": fs_enc})
            except Exception:
                pass
            return merged
        except Exception:
            pass
    # brand-new user: inherit safe defaults (no key yet)
    return dict(DEFAULT_CONFIG)


def save_config(patch: dict, uid=None) -> dict:
    """Persist a per-user config patch (merges). Dual write: file + Firestore."""
    u = safe_uid(uid if uid is not None else get_uid())
    if u == _OWNER:
        path = LEGACY_CONFIG
    else:
        os.makedirs(user_dir(u), exist_ok=True)
        path = user_config_file(u)

    data = _read_json(path) or {}
    data.update(patch)
    if data.get("gemini_api_key"):
        enc = encrypt_value(data["gemini_api_key"])
        data["gemini_api_key"] = enc
        # Firestore dual write (best-effort, never block)
        if u != _OWNER and patch.get("gemini_api_key"):
            try:
                from firebase.api_keys import save_api_key_fs
                raw = patch["gemini_api_key"]
                # raw may be plain, ensure enc is correct
                hint = raw[:6] + "..." + raw[-4:] if isinstance(raw, str) and len(raw) > 10 else ""
                save_api_key_fs(u, enc, hint)
            except Exception:
                pass
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
        # atomic write: temp -> replace (crash par 00 bytes corrupt nahi hoga)
        import tempfile
        dir_name = os.path.dirname(os.path.abspath(path)) or "."
        try:
            os.makedirs(dir_name, exist_ok=True)
        except Exception:
            pass
        # fallback: if perm denied, try direct write (no temp)
        try:
            fd, tmp = tempfile.mkstemp(dir=dir_name)
        except PermissionError:
            # RunxBuild non-root fallback: direct write
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                return
            except Exception as e2:
                print(f"[UserConfig Write Error perm fallback]: {e2}")
                return
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
            os.replace(tmp, path)
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
    except Exception as e:
        # Best-effort: Firestore already saved, don't crash container
        print(f"[UserConfig Write Error]: {e}")
