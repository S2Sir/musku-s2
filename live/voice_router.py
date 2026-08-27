"""voice_router.py - Ultra-light fast voice router.

- Command-like utterances only hit SmartRouter (<20ms target)
- Casual conversation → zero router overhead → Gemini Live continues instantly
- Fast execution runs in background thread — never blocks Gemini path
"""

import logging
import threading
from realtime.event_bus import bus
from realtime.turn_manager import turn_manager
from live import voice_config as cfg
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from smart_router import DEFAULT_ROUTER, FAST_CONFIDENCE
    _ROUTER_AVAILABLE = True
except Exception as e:
    logging.warning(f"Fast router dependencies not available: {e}")
    _ROUTER_AVAILABLE = False

logger = logging.getLogger("MUSKU.VoiceRouter")


class VoiceRouter:
    """Fast voice command router — non-blocking on Gemini critical path.

    Phase B-1: thin adapter. Classification + execution DONO SmartRouter
    (single authoritative front-door) se aate hain — ye sirf:
      - USER_SPEECH_FINAL se trigger karta hai
      - background thread me chala kar Gemini hot path ko block nahi karta
      - FAST_ROUTE_RESULT/FAST_ROUTE_COMPLETE publish karta hai
    `_map_to_control_intent` ab smart_router._to_control_intent se delegate
    hota hai (ek hi router->control mapping).
    """

    def __init__(self):
        self._router = None
        self._enabled = True
        self._lock = threading.Lock()
        self._stats = {
            "total_speech": 0,
            "fast_routes": 0,
            "gemini_routes": 0,
            "skipped_router": 0,
            "errors": 0,
        }

        if _ROUTER_AVAILABLE:
            # Phase B-1: single authoritative instance — config/state shared with
            # control.py / brain.router (no duplicate SmartRouter).
            self._router = DEFAULT_ROUTER
        else:
            self._enabled = False

    def start(self):
        if not getattr(cfg, "VOICE_ROUTER_ENABLED", False):
            return
        if not self._enabled:
            return
        bus.subscribe("USER_SPEECH_FINAL", self._on_speech_final)

    def stop(self):
        if self._enabled:
            bus.unsubscribe("USER_SPEECH_FINAL", self._on_speech_final)

    def _on_speech_final(self, payload):
        """Non-blocking: casual → return instantly; commands → background thread.
        Single front-door: SmartRouter.route() hi decide karta hai simple vs complex."""
        if not self._enabled or self._router is None:
            return

        if isinstance(payload, str):
            text = payload
        elif isinstance(payload, dict):
            text = payload.get("text", "")
        else:
            text = str(payload) if payload else ""

        text = (text or "").strip()
        if not text:
            return

        with self._lock:
            self._stats["total_speech"] += 1

        threading.Thread(
            target=self._route_and_maybe_execute,
            args=(text,),
            daemon=True,
            name="FastRoute",
        ).start()

    def _route_and_maybe_execute(self, text: str):
        try:
            route_result, result = self._router.front_door(text)
            if route_result is None:
                with self._lock:
                    self._stats["errors"] += 1
                return
            if (
                result is not None
                and route_result.fast_path
                and route_result.confidence >= FAST_CONFIDENCE
            ):
                self._publish_fast_route(route_result, text, result)
                return
            with self._lock:
                self._stats["gemini_routes"] += 1
        except Exception as e:
            logger.error(f"Voice routing error: {e}")
            with self._lock:
                self._stats["errors"] += 1

    def _publish_fast_route(self, route_result, original_text, result):
        with self._lock:
            self._stats["fast_routes"] += 1
        intent, data = self._map_to_control_intent(route_result, original_text)
        payload = {
            "success": True,
            "intent": route_result.intent,
            "control_intent": intent,
            "result": result,
            "original_text": original_text,
            "turn_id": turn_manager.get_current_turn(),
        }
        bus.publish("FAST_ROUTE_RESULT", payload)
        bus.publish("FAST_ROUTE_COMPLETE", payload)
        logger.info(
            "[%s] FAST_ROUTE %s -> %s",
            turn_manager.get_current_turn(),
            route_result.intent,
            (result[:80] if result else "ok"),
        )

    def _map_to_control_intent(self, route_result, original_text: str) -> tuple:
        """Router->control intent map — authoritative copy smart_router me.
        Yahan delegate karta hai taaki ek hi implementation rahe."""
        if self._router is None:
            return None, None
        return self._router._to_control_intent(route_result, original_text)

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._stats)

    def set_enabled(self, enabled: bool):
        self._enabled = enabled


voice_router = VoiceRouter()
