import base64
import hashlib
import json
import os
import platform

from cryptography.fernet import Fernet

_SALT = b"MUSKU_AI_SALT_2026"


def _get_machine_id():
    return platform.node() or "unknown"


def _derive_key():
    material = (_get_machine_id() + _SALT.decode()).encode()
    derived = hashlib.pbkdf2_hmac("sha256", material, _SALT, 100_000, dklen=32)
    return base64.urlsafe_b64encode(derived)


def _get_fernet():
    return Fernet(_derive_key())


SENSITIVE_KEYS = {"google_search_key", "google_cx", "gemini_api_key"}


def encrypt_value(value):
    if not value:
        return value
    f = _get_fernet()
    return f.encrypt(value.encode()).decode()


def decrypt_value(value):
    if not value:
        return value
    # Handle multi-layer encryption (config may be saved repeatedly)
    cur = value
    for _ in range(10):
        if not isinstance(cur, str) or not cur.startswith("gAAAA"):
            break
        try:
            f = _get_fernet()
            nxt = f.decrypt(cur.encode()).decode()
            if nxt == cur:
                break
            cur = nxt
        except Exception:
            break
    return cur


def encrypt_config(data):
    result = {}
    for k, v in data.items():
        if k in SENSITIVE_KEYS and isinstance(v, str):
            result[k] = encrypt_value(v)
        else:
            result[k] = v
    return result


def decrypt_config(data):
    result = {}
    for k, v in data.items():
        if k in SENSITIVE_KEYS and isinstance(v, str):
            result[k] = decrypt_value(v)
        else:
            result[k] = v
    return result


def migrate_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if not os.path.exists(config_path):
        return False
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        needs_migration = False
        for key in SENSITIVE_KEYS:
            val = data.get(key, "")
            if val and not val.startswith("gAAAA"):
                needs_migration = True
                break
        if not needs_migration:
            return False
        encrypted = encrypt_config(data)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(encrypted, f, indent=4, ensure_ascii=False)
        return True
    except Exception:
        return False