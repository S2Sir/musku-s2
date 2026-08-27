"""search_hook.py — USER_SPEECH_FINAL pe instant Google search + Live inject."""
from __future__ import annotations

import logging
import threading

from realtime.event_bus import bus

logger = logging.getLogger("MUSKU.InstantSearch")


class InstantSearchHook:
    def __init__(self):
        self._busy = threading.Lock()
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        bus.subscribe("USER_SPEECH_FINAL", self._on_speech)
        logger.info("InstantSearchHook active — live voice search enabled")

    def stop(self):
        if not self._running:
            return
        self._running = False
        bus.unsubscribe("USER_SPEECH_FINAL", self._on_speech)

    def _on_speech(self, payload):
        if isinstance(payload, str):
            text = payload
        elif isinstance(payload, dict):
            text = payload.get("text") or ""
        else:
            text = str(payload or "")
        text = text.strip()
        if not text:
            return
        threading.Thread(
            target=self._run,
            args=(text,),
            daemon=True,
            name="InstantSearch",
        ).start()

    def _run(self, text: str):
        if not self._busy.acquire(blocking=False):
            return
        try:
            from live.instant_search import (
                build_inject_prompt,
                is_search_command,
                is_search_follow_up,
                resolve_search_explain,
            )
            if not is_search_command(text) and not is_search_follow_up(text):
                return
            hit = resolve_search_explain(text)
            if not hit or not hit.get("ok"):
                return
            prompt = build_inject_prompt(hit)
            self._inject(prompt)
        except Exception as exc:
            logger.warning("Instant search failed: %s", exc)
        finally:
            self._busy.release()

    @staticmethod
    def _inject(prompt: str):
        # Browser inline Live (primary UI path)
        try:
            from live import voice_config as cfg
            if getattr(cfg, "MUSKU_INLINE_LIVE", False) and cfg.BROWSER_LIVE_WS:
                from live.browser_live_ws import browser_live_ws
                from tenant_ctx import get_uid
                browser_live_ws.send_proactive_prompt_direct(prompt, uid=get_uid())
        except Exception as exc:
            logger.debug("browser inject: %s", exc)


instant_search_hook = InstantSearchHook()
