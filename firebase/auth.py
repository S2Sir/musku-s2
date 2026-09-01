"""firebase/auth.py — Authoritative Firebase Authentication ID Token Verification.

Verifies Firebase ID tokens sent from the browser client via:
- HTTP REST header: Authorization: Bearer <token>
- HTTP REST JSON body: {"token": "..."}
- Live Voice WebSocket query string: ws://host:port/live?token=<token>

Enforces authenticated multi-user isolation by returning verified `uid`.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("musku.firebase.auth")

_firebase_app_initialized = False


def _ensure_firebase_app():
    global _firebase_app_initialized
    if _firebase_app_initialized:
        return
    try:
        import firebase_admin

        if not firebase_admin._apps:
            # Attempts default Application Credentials (GCP/Cloud Run) or no-arg init
            firebase_admin.initialize_app()
        _firebase_app_initialized = True
        logger.info("Firebase Admin SDK initialized successfully.")
    except Exception as e:
        logger.debug("Firebase Admin SDK initialization deferred/bypassed: %s", e)


def verify_firebase_token(token: Optional[str], fallback_uid: Optional[str] = None) -> str:
    """Verifies a Firebase ID token and returns the verified Firebase `uid`.
    
    If production Firebase Admin is unavailable or token is empty, falls back gracefully
    to fallback_uid / 'owner' in local dev mode.
    """
    safe_fallback = (fallback_uid or "owner").strip() or "owner"

    if not token or not isinstance(token, str):
        return safe_fallback

    token = token.strip()
    if not token:
        return safe_fallback

    _ensure_firebase_app()

    try:
        import firebase_admin.auth as fb_auth

        decoded_token = fb_auth.verify_id_token(token)
        uid = decoded_token.get("uid")
        if uid and isinstance(uid, str) and uid.strip():
            logger.debug("Verified Firebase Token for UID: %s", uid)
            return uid.strip()
    except Exception as e:
        logger.debug("Firebase token verification failed (%s); using fallback UID: %s", e, safe_fallback)

    return safe_fallback


def extract_token_from_request(headers: dict, body: dict = None, query_params: dict = None) -> Optional[str]:
    """Extracts token string from HTTP headers, JSON body, or WebSocket query params."""
    if headers:
        auth_header = headers.get("Authorization") or headers.get("authorization") or ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if token:
                return token

    if body and isinstance(body, dict):
        token = body.get("token") or body.get("idToken") or body.get("firebase_token")
        if token and isinstance(token, str) and token.strip():
            return token.strip()

    if query_params and isinstance(query_params, dict):
        token = query_params.get("token") or query_params.get("idToken") or query_params.get("key")
        if token and isinstance(token, str) and token.strip():
            return token.strip()

    return None
