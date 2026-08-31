"""firebase/api_keys.py — Per-uid Gemini API key Firestore persistence.

100+ BYOK: har user ki AIza... key encrypted Firestore me,
redeploy wipe + per-domain localStorage gap khatam.
Gracefully falls back to file if Firestore unavailable.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger("MUSKU.ApiKeysFS")

_COLLECTION = "musku_api_keys"
_DOC = "config"


def _get_db():
    try:
        from firebase.firestore import get_firestore_client
        return get_firestore_client()
    except Exception:
        return None


def save_api_key_fs(uid: str, enc_key: str, hint: str = "") -> bool:
    if not uid or not enc_key:
        return False
    db = _get_db()
    if not db:
        return False
    try:
        # Use users/{uid}/api_key/config to align with existing /users/{uid}/* rules
        # fallback to top-level musku_api_keys if needed
        try:
            doc_ref = db.collection("users").document(uid).collection("api_key").document(_DOC)
            doc_ref.set({"key_enc": enc_key, "hint": hint, "updatedAt": _server_ts(db)}, merge=True)
            return True
        except Exception:
            pass
        doc_ref = db.collection(_COLLECTION).document(uid)
        doc_ref.set({"key_enc": enc_key, "hint": hint, "updatedAt": _server_ts(db)}, merge=True)
        return True
    except Exception as e:
        logger.debug("save_api_key_fs failed uid=%s: %s", uid, e)
        return False


def load_api_key_fs(uid: str) -> str | None:
    if not uid:
        return None
    db = _get_db()
    if not db:
        return None
    try:
        # try users/{uid}/api_key/config first
        try:
            doc = db.collection("users").document(uid).collection("api_key").document(_DOC).get(timeout=5)
            if doc and getattr(doc, "exists", False):
                data = doc.to_dict() or {}
                enc = data.get("key_enc")
                if enc:
                    return enc
        except Exception:
            pass
        doc = db.collection(_COLLECTION).document(uid).get(timeout=5)
        if doc and getattr(doc, "exists", False):
            data = doc.to_dict() or {}
            return data.get("key_enc")
    except Exception as e:
        logger.debug("load_api_key_fs failed uid=%s: %s", uid, e)
    return None


def _server_ts(db):
    try:
        from firebase_admin import firestore as _fs
        return _fs.SERVER_TIMESTAMP
    except Exception:
        try:
            from google.cloud.firestore import SERVER_TIMESTAMP as _st
            return _st
        except Exception:
            return int(time.time())
