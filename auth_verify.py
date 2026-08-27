"""auth_verify.py — Verify Firebase ID tokens (RS256) WITHOUT a service account.

Verifies Google-issued Firebase ID tokens using publicly available x509 certs.
No service-account secret is needed — only the Firebase project id (musku-ai).

Design:
  * Browser sends the Firebase ID token (from firebase.auth().currentUser.getIdToken()).
  * Server fetches Google's public signing certs (cached 1h), verifies the RS256
    signature, and checks aud/iss/exp. The verified `uid` (== Firebase user id)
    is then used to scope all storage/persona — the client-supplied `uid` is NEVER
    trusted for scoping. This closes the "spoof another user's uid" gap.

Env:
  FIREBASE_PROJECT_ID  override project id (default musku-ai)
  REQUIRE_AUTH         "true"/"1" (default) -> reject unauthenticated web requests;
                       "false" -> local-dev mode, trust client uid (owner/anon)
"""
from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.x509 import load_pem_x509_certificate

logger = logging.getLogger("MUSKU.AuthVerify")

PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "musku-ai")
ISSUER = f"https://securetoken.google.com/{PROJECT_ID}"
CERT_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/"
    "securetoken@system.gserviceaccount.com"
)

_REQUIRE_AUTH = os.environ.get("REQUIRE_AUTH", "true").lower() in ("1", "true", "yes")

_CERT_CACHE: dict = {}          # kid -> RSAPublicKey
_CERT_FETCHED = 0.0
_CERT_TTL = 3600.0
_LOCK = threading.Lock()


def require_auth() -> bool:
    return _REQUIRE_AUTH


def _b64url_decode(s: str) -> bytes:
    s = s.replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    return base64.b64decode(s)


def _fetch_certs() -> None:
    """Refresh the x509 cert cache from Google. Raises on failure."""
    global _CERT_FETCHED
    req = urllib.request.Request(CERT_URL, headers={"User-Agent": "MUSKU-Auth"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode("utf-8"))
    certs: dict = {}
    for kid, pem in data.items():
        try:
            cert = load_pem_x509_certificate(pem.encode("utf-8"))
            certs[kid] = cert.public_key()
        except Exception:
            continue
    if not certs:
        raise ValueError("no certs fetched")
    with _LOCK:
        _CERT_CACHE.clear()
        _CERT_CACHE.update(certs)
        _CERT_FETCHED = time.time()


def _get_key(kid: str) -> RSAPublicKey:
    with _LOCK:
        if kid in _CERT_CACHE and (time.time() - _CERT_FETCHED) < _CERT_TTL:
            return _CERT_CACHE[kid]
    _fetch_certs()
    with _LOCK:
        if kid not in _CERT_CACHE:
            raise ValueError("unknown kid")
        return _CERT_CACHE[kid]


def verify_id_token(token: str) -> str:
    """Verify a Firebase ID token; return the verified uid. Raise on failure."""
    if not token:
        raise ValueError("empty token")
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("malformed token")
    header = json.loads(_b64url_decode(parts[0]))
    payload = json.loads(_b64url_decode(parts[1]))
    sig = _b64url_decode(parts[2])

    kid = header.get("kid")
    if not kid:
        raise ValueError("no kid")
    key = _get_key(kid)

    signing_input = (parts[0] + "." + parts[1]).encode("ascii")
    try:
        key.verify(sig, signing_input, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        raise ValueError("bad signature")

    now = time.time()
    if payload.get("exp", 0) < now:
        raise ValueError("token expired")
    if payload.get("aud") != PROJECT_ID:
        raise ValueError("bad aud")
    if payload.get("iss") != ISSUER:
        raise ValueError("bad iss")

    uid = payload.get("uid") or payload.get("sub")
    if not uid:
        raise ValueError("no uid")
    return uid


def resolve_verified_uid(token: str | None, client_uid: str | None = None) -> str | None:
    """Return the verified uid, or None if auth is required and missing/invalid.

    Security: the verified uid (never the client-supplied `client_uid`) is what
    callers should use for storage scoping. In local-dev mode (REQUIRE_AUTH off)
    we fall back to trusting `client_uid`.
    """
    if token:
        try:
            return verify_id_token(token)
        except Exception as e:  # noqa: BLE001
            logger.warning("Firebase token verify failed: %s", e)
            if require_auth():
                return None
    if require_auth():
        return None
    return client_uid


def extract_token(headers: dict, body: dict | None = None) -> str | None:
    """Pull a bearer token from Authorization header or JSON body."""
    if not headers:
        headers = {}
    low = {str(k).lower(): v for k, v in headers.items()}
    auth = low.get("authorization") or ""
    if auth.startswith("Bearer "):
        return auth[7:].strip() or None
    if body:
        t = body.get("token")
        if t:
            return str(t)
    return None
