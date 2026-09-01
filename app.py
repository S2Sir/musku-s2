"""app.py — MUSKU 2.0 Self-Contained Web Server & Live Voice Launcher.

Run this file directly: python app.py
Serves Web UI on http://localhost:8000 and Live Voice WebSocket on ws://0.0.0.0:8770/live.
100% self-contained inside musku-2.0 directory — ready for deployment.
BUILD_VERSION = "2.0.1-v2026_09_01_1037"
"""
from __future__ import annotations

import asyncio
import http.server
import json
import mimetypes
import os
import socketserver
import sys
import threading
import time

# SECURITY: Fail-closed — prod requires auth. Local dev set REQUIRE_AUTH=false explicitly.
os.environ.setdefault("REQUIRE_AUTH", "true")

# Ensure musku-2.0 and parent workspace directory are in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(1, PARENT_DIR)

from personal_profile import boss_instruction, MUSKU_NAME
from live.browser_live_ws import browser_live_ws
from brain_core import MuskuBrain

PORT = int(os.environ.get("PORT", 8000))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# Security: request limits
MAX_API_BODY = 20 * 1024  # 20KB for /api/*
MAX_CHAT_TEXT = 2000
BLOCKED_STATIC = {"config.json", ".env", "crypto_utils.py", "musku_data", "musku_users", "musku_chat", ".git", "debug_greeting.log", "server.log", "server_err.log"}
ALLOWED_STATIC_PREFIXES = ("/img/", "/js/", "/ui_theme.css", "/auth.js", "/auth.css", "/index.html", "/", "/favicon.ico", "/how-to-use.html", "/guide.html", "/user-guide.html", "/activate.html", "/admin.html", "/signup.html")

# CORS allowlist (comma-separated env). Empty => deny except same-origin. Use * only for local dev if explicitly set.
def _allowed_origins():
    raw = os.environ.get("ALLOWED_ORIGIN", "")
    if raw.strip() == "*":
        return None  # wildcard explicit
    if not raw.strip():
        return {"https://musku-ai.web.app", "https://musku-ai.firebaseapp.com", "http://localhost:8000", "http://127.0.0.1:8000"}
    return {o.strip() for o in raw.split(",") if o.strip()}

def _cors_origin(request_origin: str) -> str:
    allowed = _allowed_origins()
    if allowed is None:
        return "*"
    if request_origin and request_origin in allowed:
        return request_origin
    # Vercel preview/prod: allow any *.vercel.app (deployment URLs vary)
    if request_origin and request_origin.endswith(".vercel.app"):
        return request_origin
    # RunxBuild / PaaS: allow any *.runxbuild.app
    if request_origin and (request_origin.endswith(".runxbuild.app") or ".runxbuild." in request_origin):
        return request_origin
    # Railway PaaS: allow any *.railway.app or *.up.railway.app
    if request_origin and (".railway.app" in request_origin or ".up.railway.app" in request_origin):
        return request_origin
    # no Origin header (same-origin fetch / curl) => allow
    if not request_origin:
        return next(iter(allowed)) if allowed else "*"
    return ""  # not allowed => empty (caller will not set header or will deny)

# Per-uid rate limiter (lightweight, in-memory). Full distributed limiter = Phase 5.
_RATE = {}
_RATE_WINDOW = 60.0
_RATE_MAX = 30


def _rate_ok(uid: str) -> bool:
    now = time.time()
    hits = _RATE.get(uid)
    if not hits:
        _RATE[uid] = [now]
        return True
    hits = [t for t in hits if now - t < _RATE_WINDOW]
    if len(hits) >= _RATE_MAX:
        _RATE[uid] = hits
        return False
    hits.append(now)
    _RATE[uid] = hits
    return True


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                raw = f.read()
            # null-byte / empty file = corrupt (911x 0x00 jaisa case)
            if not raw or not raw.strip() or not raw.strip("\x00").strip():
                raise ValueError("empty or null-byte config")
            data = json.loads(raw)
            if data.get("gemini_api_key"):
                try:
                    from crypto_utils import decrypt_value
                    data["gemini_api_key"] = decrypt_value(data["gemini_api_key"])
                except Exception:
                    data["gemini_api_key"] = data["gemini_api_key"].strip()
            return data
        except Exception as e:
            print(f"[WARN] config.json corrupt/invalid ({e}) - using defaults. File: {CONFIG_FILE}")
            # backup corrupt file so restore possible, then continue with defaults
            try:
                corrupt_backup = CONFIG_FILE + ".corrupt.bak"
                if os.path.getsize(CONFIG_FILE) > 0:
                    import shutil
                    shutil.copy2(CONFIG_FILE, corrupt_backup)
                    print(f"   -> corrupt backup saved to {corrupt_backup}")
            except Exception:
                pass
            return {"user_name": "S2", "language": "hinglish"}
    return {"user_name": "S2", "language": "hinglish"}


class MuskuHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serve static web assets (index.html, ui_theme.css, img) & handle API endpoints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def end_headers(self):
        req_origin = self.headers.get("Origin", "")
        allowed_origin = _cors_origin(req_origin)
        if allowed_origin:
            self.send_header("Access-Control-Allow-Origin", allowed_origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, X-Musku-Key, X-Musku-Uid",
        )
        # Security headers
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        super().end_headers()

    def _bearer_token(self):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:].strip() or None
        return None

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        clean_p = self.path.split("?")[0].rstrip("/")
        if clean_p in ("/api/start", ""):
            clean_p = "/api/start"
        if clean_p == "/api/start":
            # Size cap
            clen = int(self.headers.get("Content-Length", 0) or 0)
            if clen > MAX_API_BODY:
                self.send_response(413)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "payload too large"}).encode("utf-8"))
                return
            try:
                try:
                    raw = (self.rfile.read(clen) or b"{}")
                    if len(raw) > MAX_API_BODY:
                        raise ValueError("payload too large")
                    body = json.loads(raw.decode("utf-8"))
                except Exception:
                    body = {}
                from auth_verify import extract_token, resolve_verified_uid
                token = extract_token(dict(self.headers), body)
                uid = resolve_verified_uid(token, body.get("uid"))
                if uid is None:
                    self.send_response(401)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "unauthorized"}).encode("utf-8"))
                    return
                from live.browser_live_ws import browser_live_ws
                # preserve greeting script if client sent one — sanitize to prevent prompt injection
                script = None
                try:
                    raw_script = (body.get("greet") or body.get("script") or "")
                    if isinstance(raw_script, str):
                        s = raw_script.strip()[:80]
                        # block injection markers
                        if "[INTERNAL" not in s and "SYSTEM" not in s.upper() and "IGNORE" not in s.upper():
                            # allow only safe chars
                            s = s.replace("[","").replace("]","").replace("\n"," ").strip()
                            script = s or None
                except Exception:
                    script = None
                browser_live_ws.send_start_greeting(uid, script=script)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))
            except Exception as e:
                # Don't leak internal details
                print(f"[API /api/start error] {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "internal"}).encode("utf-8"))
            return

        if self.path in ("/api/chat", "/api/chat/"):
            content_length = int(self.headers.get("Content-Length", 0) or 0)
            if content_length > MAX_API_BODY:
                self.send_response(413)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "payload too large"}).encode("utf-8"))
                return
            post_data = self.rfile.read(content_length)
            if len(post_data) > MAX_API_BODY:
                self.send_response(413)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "payload too large"}).encode("utf-8"))
                return
            try:
                data = json.loads(post_data.decode("utf-8"))
                raw_text = data.get("text", "")
                # Validate input
                if not isinstance(raw_text, str):
                    raw_text = str(raw_text)
                if len(raw_text) > MAX_CHAT_TEXT:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "text too long"}).encode("utf-8"))
                    return
                # Block prompt injection markers in user text (store separately, don't forward as instruction)
                if "[INTERNAL" in raw_text or "[SYSTEM" in raw_text:
                    raw_text = raw_text.replace("[INTERNAL","").replace("[SYSTEM","")
                text = raw_text
                from auth_verify import extract_token, resolve_verified_uid
                token = extract_token(dict(self.headers), data)
                uid = resolve_verified_uid(token, data.get("uid"))
                if uid is None:
                    self.send_response(401)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "unauthorized"}).encode("utf-8"))
                    return
                # Per-uid rate limit (lightweight in-memory; full Phase 5 later)
                if not _rate_ok(uid):
                    self.send_response(429)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "rate limited"}).encode("utf-8"))
                    return
                raw_key = data.get("key") or self.headers.get("X-Musku-Key") or None

                # Multi-tenant: scope config + storage to this user's VERIFIED uid.
                from user_context import set_uid, load_config, save_config
                set_uid(uid)
                cfg = load_config(uid)
                if raw_key:
                    # browser-supplied per-user Gemini key — persist per-uid so next request reuses without re-entering
                    raw_key = str(raw_key).strip()
                    if raw_key:
                        try:
                            save_config({"gemini_api_key": raw_key}, uid)
                        except Exception:
                            pass
                        cfg["gemini_api_key"] = raw_key

                user_name = cfg.get("user_name", "S2")
                b = MuskuBrain(user_name, config=cfg)
                reply = b.get_response(text) if hasattr(b, "get_response") else None
                # Web fallback: agar brain ne PC-stub diya ya empty diya to direct Gemini se jawab lo
                if not reply or "Desktop control not active" in str(reply) or "directly control nahi kar sakti" in str(reply):
                    from brain_core import _gemini_chat
                    prompt = boss_instruction(user_name, cfg.get("language", "hinglish"))
                    # _gemini_chat expects role/content, api_key per-user
                    api_k = cfg.get("gemini_api_key") or None
                    reply = _gemini_chat([
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": text}
                    ], api_key=api_k)
                    if not reply:
                        reply = "Mujhe S2 sir ne banaya hai — boliye, kya chahiye aapko? (API key check karo, Gemini se reply nahi aaya)"
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"reply": reply}).encode("utf-8"))
            except Exception as e:
                print(f"[API /api/chat error] {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "internal"}).encode("utf-8"))
            return

        if self.path in ("/api/save-key", "/api/save-key/"):
            clen = int(self.headers.get("Content-Length", 0) or 0)
            if clen > MAX_API_BODY:
                self.send_response(413)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "payload too large"}).encode("utf-8"))
                return
            try:
                raw = (self.rfile.read(clen) or b"{}")
                body = json.loads(raw.decode("utf-8"))
                from auth_verify import extract_token, resolve_verified_uid
                token = extract_token(dict(self.headers), body)
                uid = resolve_verified_uid(token, body.get("uid"))
                if uid is None:
                    self.send_response(401)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "unauthorized"}).encode("utf-8"))
                    return
                raw_key = (body.get("key") or body.get("gemini_api_key") or "").strip()
                import re as _re
                if not _re.match(r"^AIza[0-9A-Za-z\-_]{35,}$", raw_key):
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "invalid_key"}).encode("utf-8"))
                    return
                from user_context import save_config
                save_config({"gemini_api_key": raw_key}, uid)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))
            except Exception as e:
                print(f"[API /api/save-key error] {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "internal"}).encode("utf-8"))
            return

        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "not found"}).encode("utf-8"))

    def do_GET(self):
        clean_p = self.path.split("?")[0].rstrip("/")
        if clean_p in ("/api/start", "/api/start/"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))
            return
        # Health check for PaaS (RunxBuild/HF/Render) - must be 200 without auth
        if clean_p in ("/health", "/api/health"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "service": "musku-2.0"}).encode("utf-8"))
            return
        # Block sensitive files
        blocked = ("/config.json", "/.env", "/crypto_utils.py", "/debug_greeting.log", "/server.log", "/server_err.log", "/musku_data", "/musku_users", "/musku_chat", "/.git")
        for b in blocked:
            if self.path == b or self.path.startswith(b + "/") or self.path.startswith(b):
                if b in ("/musku_data", "/musku_users", "/musku_chat", "/.git") and not self.path.startswith(b + "/"):
                    continue
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "not found"}).encode("utf-8"))
                return
        # Only allow whitelisted static prefixes
        if self.path not in ("/", "", "/index.html") and not any(self.path.startswith(p) for p in ["/img/", "/js/", "/ui_theme.css", "/auth.js", "/auth.css", "/favicon.ico", "/how-to-use.html", "/activate.html", "/admin.html", "/signup.html"]):
            # Fall back to super which will 404 if file not found, but also block directory listing for unknown paths
            if ".." in self.path or self.path.startswith("/."):
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "not found"}).encode("utf-8"))
                return
        if clean_p in ("/guide", "/guide.html", "/user-guide", "/user-guide.html"):
            self.path = "/how-to-use.html"
        if self.path in ("/", ""):
            self.path = "/index.html"
        return super().do_GET()

    def end_headers(self):
        clean_p = self.path.split("?")[0]
        if clean_p.endswith(".html") or clean_p in ("/", ""):
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        else:
            self.send_header("Cache-Control", "public, max-age=60")
        super().end_headers()


def start_http_server():
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    with http.server.ThreadingHTTPServer(("0.0.0.0", PORT), MuskuHTTPRequestHandler) as httpd:
        print(f"[MUSKU 2.0 Web] Server live at http://0.0.0.0:{PORT}")
        httpd.serve_forever()


def _serve_static(environ, start_response, rel_path):
    """Serve a static file (html/css/js/img/gif/png) from BASE_DIR with correct MIME."""
    # Block sensitive files even via WSGI
    for b in BLOCKED_STATIC:
        if rel_path == "/" + b or rel_path == b or rel_path.startswith("/" + b + "/") or rel_path.startswith(b + "/"):
            return None
        if rel_path.lstrip("/") == b:
            return None
    # Allowlist check
    if rel_path not in ("/", "", "/index.html") and not any(rel_path.startswith(p) for p in ALLOWED_STATIC_PREFIXES):
        if ".." in rel_path or "/." in rel_path:
            return None
    if rel_path in ("/guide", "/guide.html", "/user-guide", "/user-guide.html"):
        rel_path = "/how-to-use.html"
    if rel_path in ("", "/"):
        rel_path = "/index.html"
    # Normalize and prevent path traversal outside BASE_DIR
    clean = os.path.normpath(rel_path).lstrip("/\\")
    full = os.path.join(BASE_DIR, clean)
    if not os.path.abspath(full).startswith(os.path.abspath(BASE_DIR)) or not os.path.isfile(full):
        return None
    mime, _ = mimetypes.guess_type(full)
    mime = mime or "application/octet-stream"
    try:
        with open(full, "rb") as f:
            data = f.read()
    except Exception:
        return None
    req_origin = environ.get("HTTP_ORIGIN", "")
    allowed_origin = _cors_origin(req_origin)
    cache_val = "no-cache, must-revalidate" if (mime and "html" in mime) else "public, max-age=120"
    headers = [
        ("Content-Type", mime),
        ("Content-Length", str(len(data))),
        ("Cache-Control", cache_val),
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
    ]
    if allowed_origin:
        headers.append(("Access-Control-Allow-Origin", allowed_origin))
        headers.append(("Vary", "Origin"))
    start_response("200 OK", headers)
    return [data]


def handler(environ, start_response):
    """WSGI entrypoint for Vercel / Python runtime."""
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")
    # Health check for PaaS (RunxBuild) - before auth
    if method == "GET" and path in ("/health", "/health/", "/api/health", "/api/health/"):
        start_response("200 OK", [("Content-Type", "application/json")])
        return [json.dumps({"status": "ok", "service": "musku-2.0"}).encode("utf-8")]
    
    if method == "OPTIONS":
        req_origin = environ.get("HTTP_ORIGIN", "")
        allowed_origin = _cors_origin(req_origin)
        hdrs = [
            ("Content-Type", "application/json"),
            ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Musku-Key, X-Musku-Uid"),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
        ]
        if allowed_origin:
            hdrs.append(("Access-Control-Allow-Origin", allowed_origin))
            hdrs.append(("Vary", "Origin"))
        start_response("200 OK", hdrs)
        return [b""]

    if method == "POST" and path in ("/api/start", "/api/start/"):
        try:
            length = int(environ.get("CONTENT_LENGTH", 0) or 0)
            if length > MAX_API_BODY:
                start_response("413 Payload Too Large", [("Content-Type", "application/json")])
                return [json.dumps({"error": "payload too large"}).encode("utf-8")]
            body_bytes = environ["wsgi.input"].read(length) if length > 0 else b"{}"
            if len(body_bytes) > MAX_API_BODY:
                start_response("413 Payload Too Large", [("Content-Type", "application/json")])
                return [json.dumps({"error": "payload too large"}).encode("utf-8")]
            body = json.loads(body_bytes.decode("utf-8"))
            from auth_verify import extract_token, resolve_verified_uid
            headers_dict = {k.replace("HTTP_", "").replace("_", "-").title(): v for k, v in environ.items() if k.startswith("HTTP_")}
            token = extract_token(headers_dict, body)
            uid = resolve_verified_uid(token, body.get("uid"))
            if uid is None:
                start_response("401 Unauthorized", [("Content-Type", "application/json")])
                return [json.dumps({"error": "unauthorized"}).encode("utf-8")]
            # sanitize script
            try:
                raw_script = (body.get("greet") or body.get("script") or "")
                script = None
                if isinstance(raw_script, str):
                    s = raw_script.strip()[:80]
                    if "[INTERNAL" not in s and "SYSTEM" not in s.upper() and "IGNORE" not in s.upper():
                        s = s.replace("[","").replace("]","").replace("\n"," ").strip()
                        script = s or None
                from live.browser_live_ws import browser_live_ws
                browser_live_ws.send_start_greeting(uid, script=script)
            except Exception:
                pass
            req_origin = environ.get("HTTP_ORIGIN", "")
            allowed_origin = _cors_origin(req_origin)
            hdrs = [("Content-Type", "application/json"), ("X-Content-Type-Options", "nosniff")]
            if allowed_origin:
                hdrs.append(("Access-Control-Allow-Origin", allowed_origin))
                hdrs.append(("Vary", "Origin"))
            start_response("200 OK", hdrs)
            return [json.dumps({"status": "ok"}).encode("utf-8")]
        except Exception as e:
            print(f"[WSGI /api/start error] {e}")
            start_response("500 Internal Error", [("Content-Type", "application/json")])
            return [json.dumps({"error": "internal"}).encode("utf-8")]

    if method == "POST" and path in ("/api/chat", "/api/chat/"):
        try:
            length = int(environ.get("CONTENT_LENGTH", 0) or 0)
            if length > MAX_API_BODY:
                start_response("413 Payload Too Large", [("Content-Type", "application/json")])
                return [json.dumps({"error": "payload too large"}).encode("utf-8")]
            body_bytes = environ["wsgi.input"].read(length) if length > 0 else b"{}"
            if len(body_bytes) > MAX_API_BODY:
                start_response("413 Payload Too Large", [("Content-Type", "application/json")])
                return [json.dumps({"error": "payload too large"}).encode("utf-8")]
            data = json.loads(body_bytes.decode("utf-8"))
            raw_text = data.get("text", "")
            if not isinstance(raw_text, str):
                raw_text = str(raw_text)
            if len(raw_text) > MAX_CHAT_TEXT:
                start_response("400 Bad Request", [("Content-Type", "application/json")])
                return [json.dumps({"error": "text too long"}).encode("utf-8")]
            if "[INTERNAL" in raw_text or "[SYSTEM" in raw_text:
                raw_text = raw_text.replace("[INTERNAL","").replace("[SYSTEM","")
            text = raw_text
            
            from auth_verify import extract_token, resolve_verified_uid
            headers_dict = {k.replace("HTTP_", "").replace("_", "-").title(): v for k, v in environ.items() if k.startswith("HTTP_")}
            token = extract_token(headers_dict, data)
            uid = resolve_verified_uid(token, data.get("uid"))
            
            if uid is None:
                start_response("401 Unauthorized", [("Content-Type", "application/json")])
                return [json.dumps({"error": "unauthorized"}).encode("utf-8")]
            # Per-uid rate limit (mirror do_POST)
            if not _rate_ok(uid):
                start_response("429 Too Many Requests", [("Content-Type", "application/json"), ("Retry-After", "60")])
                return [json.dumps({"error": "rate limited"}).encode("utf-8")]
                
            from user_context import set_uid, load_config, save_config
            set_uid(uid)
            cfg = load_config(uid)
            # Per-user key from header/body (same as do_POST) — persist per-uid
            try:
                raw_k = data.get("key") or headers_dict.get("X-Musku-Key") or headers_dict.get("X-Musku-Key".lower()) or None
                # headers_dict is Title-Cased, check case-insensitive
                if not raw_k:
                    for hk, hv in headers_dict.items():
                        if hk.lower() == "x-musku-key" and hv:
                            raw_k = hv
                            break
                if raw_k:
                    raw_k = str(raw_k).strip()
                    if raw_k:
                        try:
                            save_config({"gemini_api_key": raw_k}, uid)
                        except Exception:
                            pass
                        cfg["gemini_api_key"] = raw_k
            except Exception:
                pass
            user_name = cfg.get("user_name", "S2")
            b = MuskuBrain(user_name, config=cfg)
            reply = b.get_response(text) if hasattr(b, "get_response") else None
            if not reply or "directly control nahi kar sakti" in str(reply) or "Desktop control not active" in str(reply):
                from brain_core import _gemini_chat
                from personal_profile import boss_instruction
                prompt = boss_instruction(user_name, cfg.get("language", "hinglish"))
                api_k = cfg.get("gemini_api_key") or None
                reply = _gemini_chat([
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text}
                ], api_key=api_k)
                if not reply:
                    reply = "Main aapki kya madad kar sakti hoon? 🥰"
            
            req_origin = environ.get("HTTP_ORIGIN", "")
            allowed_origin = _cors_origin(req_origin)
            hdrs = [("Content-Type", "application/json"), ("X-Content-Type-Options", "nosniff")]
            if allowed_origin:
                hdrs.append(("Access-Control-Allow-Origin", allowed_origin))
                hdrs.append(("Vary", "Origin"))
            start_response("200 OK", hdrs)
            return [json.dumps({"reply": reply}).encode("utf-8")]
        except Exception as e:
            print(f"[WSGI /api/chat error] {e}")
            start_response("500 Internal Error", [("Content-Type", "application/json")])
            return [json.dumps({"error": "internal"}).encode("utf-8")]

    if method == "POST" and path in ("/api/save-key", "/api/save-key/"):
        try:
            length = int(environ.get("CONTENT_LENGTH", 0) or 0)
            if length > MAX_API_BODY:
                start_response("413 Payload Too Large", [("Content-Type", "application/json")])
                return [json.dumps({"error": "payload too large"}).encode("utf-8")]
            body_bytes = environ["wsgi.input"].read(length) if length > 0 else b"{}"
            body = json.loads(body_bytes.decode("utf-8"))
            from auth_verify import extract_token, resolve_verified_uid
            headers_dict = {k.replace("HTTP_", "").replace("_", "-").title(): v for k, v in environ.items() if k.startswith("HTTP_")}
            token = extract_token(headers_dict, body)
            uid = resolve_verified_uid(token, body.get("uid"))
            if uid is None:
                start_response("401 Unauthorized", [("Content-Type", "application/json")])
                return [json.dumps({"error": "unauthorized"}).encode("utf-8")]
            raw_key = (body.get("key") or body.get("gemini_api_key") or "").strip()
            if not raw_key:
                start_response("400 Bad Request", [("Content-Type", "application/json")])
                return [json.dumps({"error": "key required"}).encode("utf-8")]
            # Validate AIza format (prevent AQ... mistakes)
            import re as _re
            if not _re.match(r"^AIza[0-9A-Za-z\-_]{35,}$", raw_key):
                start_response("400 Bad Request", [("Content-Type", "application/json")])
                return [json.dumps({"error": "invalid_key", "hint": "Key must start with AIza..."}).encode("utf-8")]
            # Optional live validate (non-blocking best-effort, don't fail on network)
            # Save via user_context (dual write Firestore + file)
            from user_context import save_config
            save_config({"gemini_api_key": raw_key}, uid)
            req_origin = environ.get("HTTP_ORIGIN", "")
            allowed_origin = _cors_origin(req_origin)
            hdrs = [("Content-Type", "application/json"), ("X-Content-Type-Options", "nosniff")]
            if allowed_origin:
                hdrs.append(("Access-Control-Allow-Origin", allowed_origin))
                hdrs.append(("Vary", "Origin"))
            start_response("200 OK", hdrs)
            return [json.dumps({"status": "ok", "hint": raw_key[:6] + "..." + raw_key[-4:]}).encode("utf-8")]
        except Exception as e:
            print(f"[WSGI /api/save-key error] {e}")
            start_response("500 Internal Error", [("Content-Type", "application/json")])
            return [json.dumps({"error": "internal"}).encode("utf-8")]

    if method == "GET" and not path.startswith("/api/"):
        result = _serve_static(environ, start_response, path)
        if result is not None:
            return result

    start_response("404 Not Found", [("Content-Type", "application/json")])
    return [json.dumps({"error": "not found"}).encode("utf-8")]

_ws_started = False
_ws_lock = threading.Lock()

def _ensure_ws_started():
    global _ws_started
    if not _ws_started:
        with _ws_lock:
            if not _ws_started:
                try:
                    if not getattr(browser_live_ws, "running", False):
                        browser_live_ws.start()
                except Exception:
                    pass
                _ws_started = True

# Top-level WSGI entrypoint for Gunicorn / Vercel
app = handler


def main():
    print("==================================================")
    print("MUSKU 2.0 - Web AI Companion Server")
    print("==================================================")
    print(f"[MUSKU] Binding HTTP server on 0.0.0.0:{PORT}")

    # CRITICAL FOR RAILWAY PaaS: Start HTTP server FIRST on a daemon thread
    # so the port is listening immediately for Railway health checks.
    http_thread = threading.Thread(target=start_http_server, daemon=True, name="MuskuHTTP")
    http_thread.start()
    print(f"[MUSKU] HTTP server thread started on 0.0.0.0:{PORT}")

    # Now start Live WebSocket Voice Server (non-critical for initial load)
    try:
        browser_live_ws.start()
        print(f"[LiveWS] Voice WebSocket started")
    except Exception as e:
        print(f"[LiveWS Warning]: {e}")

    try:
        cfg = load_config()
        print(f"User Name: {cfg.get('user_name', 'aap')}")
        print(f"Language: {cfg.get('language', 'hinglish')}")
    except Exception as e:
        print(f"[Config Warning]: {e}")

    print(f"\nMUSKU 2.0 Web is 100% Ready! Open: http://0.0.0.0:{PORT}\n")

    # Block main thread forever (daemon threads keep running)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 MUSKU Web Server stopping...")
        browser_live_ws.stop()


if __name__ == "__main__":
    main()
