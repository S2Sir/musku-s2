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
            key = (data.get("gemini_api_key") or data.get("google_api_key") or "").strip()
            if key:
                return key
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

    def send_start_greeting(self, uid=None):
        """START dabane par greeting — queue-safe per user.

        Session connected hai toh direct send; warna us uid ke liye pending queue
        karo (connect par flush). uid None ho toh last user ke liye queue."""
        sess, loop = self._target(uid)
        if sess and loop and getattr(sess, "active", False):
            try:
                asyncio.run_coroutine_threadsafe(sess.send_greeting(), loop)
            except Exception as e:
                logger.debug("send_start_greeting inline: %s", e)
        else:
            key = uid or self._last_uid or "_default_"
            self._pending_greetings[key] = True

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
            "reminder naturally bolo. Feminine, hamesha aap + Boss. Tool mat use karo.]\n"
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

    async def _async_main(self):
        host = getattr(cfg, "BROWSER_LIVE_WS_HOST", "127.0.0.1")
        port = int(getattr(cfg, "BROWSER_LIVE_WS_PORT", 3000))
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
        path = self._ws_path(ws)
        if path and path.split("?")[0] not in _LIVE_PATHS:
            await ws.close(1008, "invalid path")
            return
        # Multi-tenant: extract raw uid, token from query string
        from user_context import extract_uid_from_query
        raw_uid = extract_uid_from_query(path or "")
        token = None
        try:
            from urllib.parse import parse_qs
            qs = path.split("?", 1)[1] if "?" in (path or "") else ""
            qd = parse_qs(qs)
            token = (qd.get("token", [None])[0]) or (qd.get("idToken", [None])[0]) or None
        except Exception:
            token = None

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

        await self._handler_inline_live(ws, uid=uid, key=None, token=token)

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

        # Per-user Gemini key required for web users (no shared owner key fallback).
        if vuid:
            api_key = key or uconfig.get("gemini_api_key") or None
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
            boss_name=user_name, language=language, relationship_mode=rel_mode
        )
        session = MuskuLiveSession(ws, api_key, system_prompt)
        with self._lock:
            self._sessions[ukey] = session
            self._last_uid = ukey
        # flush this user's queued greeting (set by /api/start before connect)
        if self._pending_greetings.pop(ukey, False):
            session._greet_on_connect = True
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
