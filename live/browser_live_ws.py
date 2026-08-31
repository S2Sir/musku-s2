"""browser_live_ws.py - Browser /live WebSocket (Musku inline Live).

Har /live client = apna Gemini session (musku_live_session.py); audio/video/text
seedha browser ↔ Gemini. No legacy transport / client.py dependency.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from typing import Any, Optional, Set

import websockets
from websockets.exceptions import ConnectionClosed

from live import voice_config as cfg

logger = logging.getLogger("MUSKU.BrowserLiveWS")
# Silence noisy probe EOF spam that causes log bloat → OOM 137 on RunxBuild
for _lname in ("websockets.server", "websockets.asyncio.server"):
    try:
        _wl = logging.getLogger(_lname)
        _wl.setLevel(logging.WARNING)
        # filter EOF probe: don't log handshake failed for empty request
        class _ProbeFilter(logging.Filter):
            def filter(self, record):
                msg = record.getMessage() if hasattr(record, "getMessage") else str(record.msg) if hasattr(record, "msg") else ""
                if "EOFError" in msg or "opening handshake failed" in msg or "InvalidMessage" in msg:
                    # only suppress if stack is probe (no path), keep real errors with stack
                    return False
                return True
        _wl.addFilter(_ProbeFilter())
    except Exception:
        pass

_LIVE_PATHS = frozenset({"/live", "/live/"})


def _load_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    if key:
        return key.strip()
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, "..", "config.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw = (data.get("gemini_api_key") or data.get("google_api_key") or "").strip()
            if raw:
                try:
                    from crypto_utils import decrypt_value
                    dec = decrypt_value(raw)
                    if dec and dec.strip():
                        return dec.strip()
                except Exception:
                    pass
                return raw
    except Exception:
        pass
    return ""


def _load_voice_gain() -> float:
    """Browser speaker softness gain (masterGain). config.json `musku_voice_gain`."""
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, "..", "config.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        gain = float(data.get("musku_voice_gain", 2.4))
        return gain if gain > 0.0 else 2.4
    except Exception:
        return 2.4


class BrowserLiveWSServer:
    """Browser /live WebSocket — Musku inline Live or legacy transport."""

    def __init__(self):
        self._clients: Set[Any] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._server = None
        self._lock = threading.Lock()
        # Multi-tenant: har uid ki apni MuskuLiveSession (single _active_session hata diya)
        self._sessions: dict = {}
        # Per-uid persona/language override (NOT global — otherwise one user's
        # switch leaks into another user's Live session: Phase 4 isolation).
        self._system_prompt_overrides: dict = {}
        self._pending_greetings: dict = {}  # uid -> pending greeting flag
        self._last_uid = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    @property
    def gemini_connected(self) -> bool:
        sess = self._sessions.get(self._last_uid) if self._last_uid else None
        return sess is not None and getattr(sess, "active", False)

    def start(self):
        if not cfg.BROWSER_LIVE_WS:
            return
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._thread_main, daemon=True, name="BrowserLiveWS"
        )
        self._thread.start()

    def stop(self):
        loop = self._loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self._async_stop(), loop)

    def _target(self, uid=None):
        """Resolve (session, loop) for a uid; fallback to last / any session."""
        with self._lock:
            if uid and uid in self._sessions:
                sess = self._sessions[uid]
            elif self._last_uid and self._last_uid in self._sessions:
                sess = self._sessions[self._last_uid]
            elif self._sessions:
                sess = next(iter(self._sessions.values()))
            else:
                sess = None
        return sess, self._loop

    def send_realtime_text(self, text: str, uid=None):
        """Realtime text — target user's session (fallback: last session)."""
        sess, loop = self._target(uid)
        if not sess or not loop or not text:
            return
        try:
            asyncio.run_coroutine_threadsafe(sess.send_realtime_text(text), loop)
        except Exception as e:
            logger.debug("send_realtime_text: %s", e)

    def send_client_text(self, text: str, uid=None):
        """Full user-turn inject — target user's MuskuLiveSession."""
        if not text:
            return
        sess, loop = self._target(uid)
        if sess and loop and getattr(sess, "active", False):
            try:
                asyncio.run_coroutine_threadsafe(sess.send_client_text(str(text)), loop)
            except Exception as e:
                logger.debug("send_client_text inline: %s", e)

    def update_system_prompt(self, prompt: str, uid=None):
        """Language/persona update — target user's session (reconnect par bhi).

        Override is stored PER-UID (not globally) so one user's persona/language
        switch never leaks into another user's Live session (Phase 4 isolation).
        """
        if not prompt:
            return
        key = uid or self._last_uid or "_default_"
        self._system_prompt_overrides[key] = str(prompt)
        sess, loop = self._target(uid)
        if sess and loop and getattr(sess, "active", False):
            try:
                asyncio.run_coroutine_threadsafe(sess.update_system_prompt(str(prompt)), loop)
            except Exception as e:
                logger.debug("update_system_prompt inline: %s", e)

    def send_start_greeting(self, uid=None, script=None):
        """START dabane par greeting — queue-safe per user, force fresh turn.

        Session connected hai toh direct send (force=True har tap par);
        warna us uid ke liye pending queue karo (script preserve, connect par flush)."""
        sess, loop = self._target(uid)
        if sess and loop and getattr(sess, "active", False):
            try:
                asyncio.run_coroutine_threadsafe(sess.send_greeting(script, force=True), loop)
            except Exception as e:
                logger.debug("send_start_greeting inline: %s", e)
        else:
            key = uid or self._last_uid or "_default_"
            self._pending_greetings[key] = script if isinstance(script, str) and script.strip() else None

    def send_proactive_prompt_direct(self, prompt: str, uid=None):
        """Proactive prompt as-is — target user's session."""
        if not prompt:
            return
        sess, loop = self._target(uid)
        if sess and loop and getattr(sess, "active", False):
            try:
                asyncio.run_coroutine_threadsafe(sess.send_proactive_prompt(str(prompt)), loop)
            except Exception as e:
                logger.debug("send_proactive_prompt_direct inline: %s", e)

    def send_proactive_message(self, text: str, uid=None):
        """Health/break reminder — Musku awaaz se bolti hai (target user)."""
        if not text:
            return
        if uid is None:
            from tenant_ctx import get_uid
            uid = get_uid() or self._last_uid
        prompt = (
            "[INTERNAL — yeh user ki baat nahi hai. Musku, awaaz se ye health/care "
            "reminder naturally bolo. Feminine, hamesha aap se pyaar se. Tool mat use karo.]\n"
            + str(text)
        )
        sess, loop = self._target(uid)
        if sess and loop and getattr(sess, "active", False):
            try:
                asyncio.run_coroutine_threadsafe(sess.send_proactive_prompt(prompt), loop)
            except Exception as e:
                logger.debug("send_proactive_message inline: %s", e)

    def send_search_context(self, text: str, uid=None):
        """Instant Google search results — Musku ko awaaz se explain karwao."""
        if not text:
            return
        prompt = str(text)
        if not prompt.startswith("[INTERNAL"):
            prompt = (
                "[INTERNAL — yeh user ki nayi command nahi. Search pehle se complete hai. "
                "Sorry/fail mat bolo. Tool mat call karo.]\n"
                + prompt
            )
        self.send_proactive_prompt_direct(prompt, uid=uid)

    def send_proactive_checkin(self, uid=None):
        """User silent ~1 min — Musku caring check-in (target user)."""
        from monitoring.user_idle_checkin import build_checkin_prompt

        prompt = build_checkin_prompt()
        sess, loop = self._target(uid)
        if sess and loop and getattr(sess, "active", False):
            try:
                asyncio.run_coroutine_threadsafe(sess.send_proactive_prompt(prompt), loop)
            except Exception as e:
                logger.debug("send_proactive_checkin inline: %s", e)

    def broadcast_resume_audio(self):
        self._broadcast({"type": "resume_audio"})

    def _thread_main(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._async_main())
        except Exception as e:
            logger.error("BrowserLiveWS loop error: %s", e)
        finally:
            try:
                loop.close()
            except Exception:
                pass

    async def _process_http(self, connection, request):
        """Single-port PaaS (RunxBuild/HF) — serve HTTP via same port as WS. /live → WS, else → app.handler."""
        try:
            path = getattr(request, "path", "") or ""
            # Let /live through to WS handshake
            if path.split("?")[0] in _LIVE_PATHS:
                return None
            # Build WSGI environ for app.handler
            import io, urllib.parse
            from app import handler as _app_handler
            method = getattr(request, "method", "GET") or "GET"
            headers = getattr(request, "headers", {}) or {}
            # websockets headers is Headers object, convert to dict
            try:
                hdr_dict = dict(headers) if hasattr(headers, "items") else {}
            except Exception:
                hdr_dict = {}
            # POST body: websockets Request has no body (handshake only). For single-port HTTP, body is not available here,
            # but /api/start only needs Authorization header (token) which is in headers, so empty body still queues greeting via token.
            # Don't try to read from connection.reader (blocks → 502), use empty.
            body = b""
            # Try request.body if ever present (future websockets version)
            try:
                b2 = getattr(request, "body", None)
                if isinstance(b2, (bytes, bytearray)) and b2:
                    body = bytes(b2)
                elif isinstance(b2, str) and b2:
                    body = b2.encode("utf-8")
            except Exception:
                body = b""
            # Parse path and query
            parsed = urllib.parse.urlparse(path)
            environ = {
                "REQUEST_METHOD": method,
                "PATH_INFO": parsed.path or "/",
                "QUERY_STRING": parsed.query or "",
                "SERVER_NAME": "localhost",
                "SERVER_PORT": str(getattr(cfg, "BROWSER_LIVE_WS_PORT", 8000)),
                "HTTP_HOST": hdr_dict.get("Host", hdr_dict.get("host", "")),
                "CONTENT_LENGTH": str(len(body)),
                "CONTENT_TYPE": hdr_dict.get("Content-Type", hdr_dict.get("content-type", "")),
                "wsgi.input": io.BytesIO(body),
                "wsgi.errors": __import__("sys").stderr,
                "wsgi.url_scheme": "https" if hdr_dict.get("X-Forwarded-Proto", "") == "https" else "http",
                "wsgi.multithread": True,
                "wsgi.multiprocess": False,
                "wsgi.run_once": False,
            }
            # Map HTTP_ headers
            for k, v in hdr_dict.items():
                kk = "HTTP_" + k.upper().replace("-", "_")
                if kk not in ("HTTP_CONTENT_TYPE", "HTTP_CONTENT_LENGTH"):
                    environ[kk] = v
            # Capture WSGI response
            status_headers = {}
            def _start_response(status, headers, exc_info=None):
                status_headers["status"] = status
                status_headers["headers"] = headers
                return lambda x: None
            result = _app_handler(environ, _start_response)
            body_out = b"".join(result) if result else b""
            status_str = status_headers.get("status", "200 OK")
            try:
                code = int(status_str.split()[0])
            except Exception:
                code = 200
            # websockets >=12 expects Response object, not tuple
            from websockets.http11 import Response
            from websockets.datastructures import Headers
            reason = status_str.split(" ", 1)[1] if " " in status_str else "OK"
            raw_hdrs = status_headers.get("headers", [])
            # Ensure Headers type
            headers_obj = Headers(raw_hdrs)
            return Response(code, reason, headers_obj, body_out)
        except Exception as e:
            logger.debug("HTTP process error: %s", e)
            from websockets.http11 import Response
            from websockets.datastructures import Headers
            return Response(500, "Internal Server Error", Headers([("Content-Type", "text/plain")]), b"internal")

    async def _async_main(self):
        # Patch websockets Request to allow POST with body for single-port HTTP (otherwise POST → 502)
        try:
            from websockets.http11 import Request as _WReq
            import re as _re2
            _orig_parse = _WReq.parse
            def _patched_parse(read_line):
                # allow GET and POST, allow Content-Length >0
                from websockets.http11 import parse_line, parse_headers
                from websockets.datastructures import Headers as _Hdrs
                try:
                    request_line = yield from parse_line(read_line)
                except Exception as exc:
                    raise
                try:
                    method, raw_path, protocol = request_line.split(b" ", 2)
                except ValueError:
                    from websockets.utils import decorators as _d
                    raise ValueError(f"invalid request line: {request_line!r}")
                if protocol != b"HTTP/1.1":
                    raise ValueError(f"unsupported protocol: {request_line!r}")
                if method not in (b"GET", b"POST", b"OPTIONS"):
                    raise ValueError(f"unsupported method: {method!r}")
                path = raw_path.decode("ascii", "surrogateescape")
                headers = yield from parse_headers(read_line)
                # allow body for POST
                return _WReq(path, headers)
            _WReq.parse = classmethod(lambda cls, read_line: _patched_parse(read_line))
        except Exception:
            pass
        host = getattr(cfg, "BROWSER_LIVE_WS_HOST", "127.0.0.1")
        port = int(getattr(cfg, "BROWSER_LIVE_WS_PORT", 3000))
        # Single-port PaaS: if WS port == HTTP PORT, serve HTTP via process_request on same port
        import os
        http_port = int(os.environ.get("PORT", "8000"))
        single_port = (port == http_port)
        if single_port:
            self._server = await websockets.serve(
                self._handler,
                host,
                port,
                ping_interval=20,
                ping_timeout=120,
                max_size=2_000_000,
                process_request=self._process_http,
            )
        else:
            self._server = await websockets.serve(
                self._handler,
                host,
                port,
                ping_interval=20,
                ping_timeout=120,
                max_size=2_000_000,
            )
        mode = "inline"
        logger.info("Browser Live WS (%s) on ws://%s:%s/live", mode, host, port)
        print(f"[LiveWS] /live on ws://{host}:{port}/live ({mode} mode)")
        try:
            await asyncio.Future()
        finally:
            if self._server:
                self._server.close()
                await self._server.wait_closed()

    async def _async_stop(self):
        for ws in list(self._clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._clients.clear()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    def _ws_path(self, ws) -> str:
        req = getattr(ws, "request", None)
        if req is not None:
            return getattr(req, "path", "") or ""
        return getattr(ws, "path", "") or ""

    async def _handler(self, ws):
        # Origin check (CSWSH protection)
        try:
            origin = ""
            req = getattr(ws, "request", None)
            if req is not None:
                origin = getattr(req, "headers", {}).get("Origin") or getattr(req, "headers", {}).get("origin") or ""
            else:
                origin = getattr(ws, "request_headers", {}).get("Origin", "") if hasattr(ws, "request_headers") else ""
            if origin:
                import os
                allowed_raw = os.environ.get("ALLOWED_ORIGIN", "")
                if allowed_raw and allowed_raw != "*":
                    allowed = {o.strip() for o in allowed_raw.split(",") if o.strip()}
                    if origin not in allowed and "https://musku-ai.web.app" not in allowed and "https://musku-ai.firebaseapp.com" not in allowed:
                        # allow PaaS wildcards (Vercel, RunxBuild) and localhost for dev
                        if origin.endswith(".vercel.app") or origin.endswith(".runxbuild.app") or ".runxbuild." in origin:
                            pass
                        elif origin not in ("http://localhost:8000","http://127.0.0.1:8000","http://localhost:8770"):
                            logger.warning("WS rejected Origin %s", origin)
                            await ws.close(1008, "origin not allowed")
                            return
        except Exception:
            pass
        path = self._ws_path(ws)
        if path and path.split("?")[0] not in _LIVE_PATHS:
            await ws.close(1008, "invalid path")
            return
        # Multi-tenant: extract raw uid, token, key from query string
        from user_context import extract_uid_from_query
        raw_uid = extract_uid_from_query(path or "")
        token = None
        key_qs = None
        try:
            from urllib.parse import parse_qs
            qs = path.split("?", 1)[1] if "?" in (path or "") else ""
            qd = parse_qs(qs)
            token = (qd.get("token", [None])[0]) or (qd.get("idToken", [None])[0]) or None
            key_qs = (qd.get("key", [None])[0]) or None
        except Exception:
            token = None
            key_qs = None

        if key_qs:
            logger.debug("WS key in query deprecated — use first-message auth; key_qs present for uid=%s", raw_uid)
        # Authoritative token verification via Firebase Auth
        from firebase.auth import verify_firebase_token
        uid = verify_firebase_token(token, fallback_uid=raw_uid)

        self._clients.add(ws)
        logger.info("Browser /live client connected verified_uid=%s (%d active)", uid, len(self._clients))
        try:
            await ws.send(json.dumps({
                "type": "voice_config",
                "gain": _load_voice_gain(),
                "mic_gain": float(getattr(cfg, "JS_MIC_GAIN", 3.0)),
            }))
        except Exception as e:
            logger.debug("voice_config send: %s", e)

        await self._handler_inline_live(ws, uid=uid, key=key_qs, token=token)

    async def _handler_inline_live(self, ws, uid=None, key=None, token=None):
        from live.musku_live_session import MuskuLiveSession

        # SECURITY: verify identity; never trust the client-supplied uid for scoping.
        from auth_verify import resolve_verified_uid
        vuid = resolve_verified_uid(token, uid)
        if vuid is None:
            try:
                await ws.send(json.dumps({"type": "error", "error": "unauthorized"}))
            except Exception:
                pass
            await ws.close(1008, "unauthorized")
            return

        # Scope all storage + persona to this VERIFIED user for the session lifetime.
        from user_context import set_uid, load_config, ensure_user_dir, save_config
        set_uid(vuid)
        uconfig = load_config(vuid)
        if key:
            # browser passed this user's own Gemini key — persist (encrypted) for reuse
            try:
                save_config({"gemini_api_key": key}, vuid)
                uconfig["gemini_api_key"] = key
            except Exception:
                pass
        ensure_user_dir(vuid)

        # Per-user Gemini key — fallback to global owner key for local-dev / anon users
        if vuid:
            api_key = key or uconfig.get("gemini_api_key") or _load_api_key() or None
            if not api_key:
                try:
                    await ws.send(json.dumps({"type": "error", "error": "API key required — add your Gemini key"}))
                except Exception:
                    pass
                await ws.close(1008, "api key required")
                return
        else:
            api_key = key or uconfig.get("gemini_api_key") or _load_api_key()

        user_name = uconfig.get("user_name", "S2")
        language = uconfig.get("language", "hinglish")
        rel_mode = uconfig.get("relationship_mode", "best_friend")
        ukey = vuid or "_default_"

        # Max ONE active Live session per uid (no double-overwrite; Phase 3/4).
        with self._lock:
            existing = self._sessions.get(ukey)
            if existing is not None and getattr(existing, "active", False):
                try:
                    await ws.send(json.dumps({"type": "error", "error": "session already active"}))
                except Exception:
                    pass
                await ws.close(1008, "already active")
                return
            self._sessions.pop(ukey, None)

        override = self._system_prompt_overrides.get(ukey)
        system_prompt = override or cfg.get_live_system_prompt(
            boss_name=user_name, language=language, relationship_mode=rel_mode, uid=vuid
        )
        session = MuskuLiveSession(ws, api_key, system_prompt, uid=vuid)
        with self._lock:
            self._sessions[ukey] = session
            self._last_uid = ukey
        # flush this user's queued greeting (set by /api/start before connect) — preserve script
        pending = self._pending_greetings.pop(ukey, None)
        if pending is not None:
            session._greet_on_connect = True
            if isinstance(pending, str):
                session._pending_greeting = pending
        try:
            await ws.send(json.dumps({"type": "status", "status": "transport_connected"}))
            await session.run()
        except ConnectionClosed:
            pass
        except Exception as e:
            logger.warning("Musku /live client error: %s", e)
        finally:
            with self._lock:
                if self._sessions.get(ukey) is session:
                    self._sessions.pop(ukey, None)
                if self._last_uid == ukey:
                    self._last_uid = None
            self._clients.discard(ws)
            logger.info("Browser /live client disconnected uid=%s (%d active)", ukey, len(self._clients))

    def _broadcast(self, obj: dict):
        loop = self._loop
        if not loop or loop.is_closed():
            return
        payload = json.dumps(obj)
        try:
            asyncio.run_coroutine_threadsafe(self._async_broadcast(payload), loop)
        except Exception:
            pass

    async def _async_broadcast(self, payload: str):
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)


browser_live_ws = BrowserLiveWSServer()
