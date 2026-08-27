"""app.py — MUSKU 2.0 Self-Contained Web Server & Live Voice Launcher.

Run this file directly: python app.py
Serves Web UI on http://localhost:8000 and Live Voice WebSocket on ws://0.0.0.0:8770/live.
100% self-contained inside musku-2.0 directory — ready for deployment.
"""
from __future__ import annotations

import asyncio
import http.server
import json
import os
import socketserver
import sys
import threading
import time

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
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("gemini_api_key"):
            data["gemini_api_key"] = data["gemini_api_key"].strip()
        return data
    return {"user_name": "S2", "language": "hinglish"}


class MuskuHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serve static web assets (index.html, ui_theme.css, img) & handle API endpoints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def end_headers(self):
        origin = os.environ.get("ALLOWED_ORIGIN", "*")
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, X-Musku-Key, X-Musku-Uid",
        )
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
        if self.path in ("/api/start", "/api/start/"):
            try:
                try:
                    body = json.loads((self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}").decode("utf-8"))
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
                browser_live_ws.send_start_greeting(uid)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        if self.path in ("/api/chat", "/api/chat/"):
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode("utf-8"))
                text = data.get("text", "")
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
                from user_context import set_uid, load_config
                set_uid(uid)
                cfg = load_config(uid)
                if raw_key:
                    # browser-supplied per-user Gemini key (already decrypted client-side)
                    cfg["gemini_api_key"] = raw_key

                user_name = cfg.get("user_name", "S2")
                b = MuskuBrain(user_name, config=cfg)
                reply = b.get_response(text) if hasattr(b, "get_response") else None
                if not reply or "Desktop control not active" in str(reply):
                    from brain_core import _gemini_chat
                    prompt = boss_instruction(user_name, cfg.get("language", "hinglish"))
                    reply = _gemini_chat([
                        {"role": "user", "parts": [{"text": text}]}
                    ])
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"reply": reply}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        if self.path in ("/", ""):
            self.path = "/index.html"
        return super().do_GET()


def start_http_server():
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    with http.server.ThreadingHTTPServer(("", PORT), MuskuHTTPRequestHandler) as httpd:
        print(f"✨ [MUSKU 2.0 Web] Server live at http://localhost:{PORT}")
        httpd.serve_forever()


def main():
    print("==================================================")
    print("💜 MUSKU 2.0 — Web AI Companion Server")
    print("==================================================")
    cfg = load_config()
    print(f"👤 Boss Name: {cfg.get('user_name', 'S2')}")
    print(f"🗣️  Language: {cfg.get('language', 'hinglish')}")

    # Start Live WebSocket Voice Server on ws://0.0.0.0:8770/live
    try:
        browser_live_ws.start()
        print("🎙️  [Live Voice WS] Server listening on ws://0.0.0.0:8770/live")
    except Exception as e:
        print(f"⚠️  Live WS Warning: {e}")

    # Start Web Asset Server on http://localhost:8000
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()

    print("\n🚀 MUSKU 2.0 Web is 100% Ready!")
    print(f"👉 Open in browser: http://localhost:{PORT}\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 MUSKU Web Server stopping...")
        browser_live_ws.stop()
        sys.exit(0)


if __name__ == "__main__":
    main()
