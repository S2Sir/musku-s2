"""orchestrator.py - Central Coordinator for the MUSKU System.

Wires mic, speaker, Gemini Live, watchdog. Voice lifecycle authority is
realtime/voice_supervisor.py (instant multi-turn).
"""

import json
import logging
import os
import threading

from realtime.event_bus import bus
from realtime.state_machine import state_machine, SystemState
from realtime.session_controller import session_controller as session
from live import voice_config as cfg
from tools.executor import tool_executor  # noqa: F401 — side-effect wiring
from monitoring.watchdog import watchdog
from realtime.voice_supervisor import voice_supervisor
from crypto_utils import decrypt_value

if cfg.VOICE_ROUTER_ENABLED:
    from live.voice_router import voice_router
else:
    voice_router = None  # type: ignore

if cfg.LOCAL_BARGE_IN_ENABLED:
    import live.barge_in  # noqa: F401 — local barge-in (echo gate mode only)

logger = logging.getLogger("MUSKU.Orchestrator")

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_FILE = os.path.join(_BASE_DIR, "..", "config.json")


def _load_api_key():
    try:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        key = data.get("gemini_api_key")
        if not key:
            return None
        return decrypt_value(key)
    except Exception:
        return None


class Orchestrator:
    def __init__(self, bridge=None):
        self.bridge = bridge
        self.speaker = None
        self.mic = None
        self._started = False
        self._watch_stop = threading.Event()
        self._setup_listeners()

    def _setup_listeners(self):
        bus.subscribe("GUI_START_REQUEST", self.start)
        bus.subscribe("GUI_STOP_REQUEST", self.stop)
        bus.subscribe("SESSION_CONNECTED", self._on_connected)
        bus.subscribe("INTERRUPT_RECEIVED", self._on_interrupt)
        bus.subscribe("TURN_COMPLETE", self._on_turn_complete)
        bus.subscribe("AI_AUDIO_CHUNK", self._on_audio_chunk)
        bus.subscribe("USER_SPEECH_FINAL", self._on_user_speech)
        bus.subscribe("USER_SPEECH_PARTIAL", self._on_user_speech_partial)
        bus.subscribe("STATE_CHANGE", self._on_state_change)
        bus.subscribe("SYSTEM_RECOVERY_INITIATED", self._on_recovery_initiated)
        bus.subscribe("FAST_ROUTE_RESULT", self._on_fast_route_result)
        bus.subscribe("FAST_ROUTE_COMPLETE", self._on_fast_route_complete)
        bus.subscribe("AUDIO_DEVICE_CHANGED", self._on_audio_device_changed)

    def start(self, payload=None):
        logger.info("Orchestrator booting up MUSKU System...")
        if self._started:
            return
        self._started = True
        state_machine.set_state(SystemState.CONNECTING)

        try:
            if cfg.VOICE_ROUTER_ENABLED and voice_router is not None:
                voice_router.start()
            else:
                logger.info("VoiceRouter disabled — Gemini owns routing")
        except Exception as e:
            logger.error(f"VoiceRouter start failed: {e}")

        try:
            if getattr(cfg, "INSTANT_SEARCH_HOOK", False):
                from live.search_hook import instant_search_hook
                instant_search_hook.start()
        except Exception as e:
            logger.error(f"InstantSearchHook start failed: {e}")

        try:
            self._watch_stop.clear()
            threading.Thread(
                target=self._gate_watch, daemon=True, name="GateWatch"
            ).start()
        except Exception:
            pass

        try:
            from audio.device_watcher import get_device_watcher
            get_device_watcher().start()
        except Exception as e:
            logger.error(f"DeviceWatcher start failed: {e}")

        from live.browser_audio_bridge import BrowserSpeakerStub
        self.speaker = BrowserSpeakerStub()
        self.speaker.start()
        voice_supervisor.set_speaker(self.speaker)

        from live.browser_mic_bridge import BrowserMicStub
        self.mic = BrowserMicStub()
        self.mic.start()
        logger.info("Browser mic mode — PyAudio MicCapture off (WebView AEC)")
        if cfg.BROWSER_LIVE_WS:
            try:
                from live.browser_live_ws import browser_live_ws
                browser_live_ws.start()
                logger.info("Browser /live WebSocket started")
            except Exception as e:
                logger.error("BrowserLiveWS start failed: %s", e)

        api_key = _load_api_key()
        if getattr(cfg, "MUSKU_INLINE_LIVE", False) and cfg.BROWSER_LIVE_WS:
            logger.info("Musku inline Live — Gemini session in /live WS (no LiveClient)")
            if api_key:
                state_machine.set_state(SystemState.LISTENING)
            else:
                bus.publish("ERROR", {
                    "source": "config",
                    "error": "API key missing — save your key in Profile settings",
                    "level": "error",
                })
                state_machine.set_state(SystemState.ERROR, context="No API Key")
        elif api_key:
            session.start(api_key)
        else:
            logger.error("No Gemini API key found — Live session not started.")
            bus.publish("ERROR", {
                "source": "config",
                "error": "API key missing — save your key in Profile settings",
                "level": "error",
            })
            state_machine.set_state(SystemState.ERROR, context="No API Key")

        try:
            watchdog.register_components(live=None, mic=self.mic, speaker=self.speaker)
            watchdog.start()
        except Exception as e:
            logger.error(f"Watchdog start failed: {e}")

    def stop(self, payload=None):
        logger.info("Orchestrator shutting down MUSKU System...")
        self._watch_stop.set()
        try:
            if cfg.VOICE_ROUTER_ENABLED and voice_router is not None:
                voice_router.stop()
        except Exception as e:
            logger.error(f"VoiceRouter stop failed: {e}")
        session.stop()
        if self.speaker is not None:
            try:
                self.speaker.close()
            except Exception:
                pass
        if self.mic is not None:
            try:
                self.mic.stop()
            except Exception:
                pass
        state_machine.set_state(SystemState.OFFLINE)

    def _on_audio_device_changed(self, payload=None):
        """Windows default audio device badla — streams fresh kholo.

        Browser mode me mic/speaker JS side restart karta hai (main.py push_js
        subscriber). PyAudio mode me yahan khud streams recover karte hain.
        """
        if getattr(cfg, "BROWSER_MIC_ENABLED", False):
            return
        if self.mic is not None:
            try:
                if hasattr(self.mic, "recover"):
                    self.mic.recover()
                else:
                    self.mic.stop()
                    self.mic.start()
            except Exception as e:
                logger.error(f"Mic restart on device change failed: {e}")
        if self.speaker is not None:
            try:
                if hasattr(self.speaker, "recover"):
                    self.speaker.recover()
                else:
                    self.speaker.close()
                    self.speaker.start()
            except Exception as e:
                logger.error(f"Speaker restart on device change failed: {e}")

    def _on_connected(self, payload=None):
        voice_supervisor.on_session_connected()

    def _on_audio_chunk(self, payload=None):
        voice_supervisor.on_ai_audio_chunk()

    def _on_user_speech(self, payload=None):
        text = payload if isinstance(payload, str) else (payload or {}).get("text", "")
        voice_supervisor.on_user_speech_final(text)

    def _on_user_speech_partial(self, payload=None):
        text = payload if isinstance(payload, str) else (payload or {}).get("text", "")
        voice_supervisor.on_user_speech_partial(text)

    def _on_state_change(self, payload=None):
        new_state = (payload or {}).get("new_state")
        if new_state:
            voice_supervisor.sync_activity_gate(new_state)

    def _on_interrupt(self, payload=None):
        voice_supervisor.on_interrupt(speaker=self.speaker)

    def _on_recovery_initiated(self, payload=None):
        """Soft reconnect — internal _run_loop handles invisible recovery."""
        try:
            session.recover()
        except Exception as e:
            logger.error(f"Live session recovery failed: {e}")

    def _on_fast_route_result(self, payload):
        if not payload or not isinstance(payload, dict):
            return
        if payload.get("success") and payload.get("result"):
            logger.debug("Fast route: %s", str(payload.get("result"))[:80])

    def _on_fast_route_complete(self, payload=None):
        success = bool((payload or {}).get("success", False))
        voice_supervisor.on_fast_route_complete(success=success)

    def _on_turn_complete(self, payload=None):
        voice_supervisor.on_turn_complete(speaker=self.speaker)

    def _gate_watch(self):
        while not self._watch_stop.wait(cfg.GATE_WATCH_INTERVAL):
            voice_supervisor.check_stuck()


orchestrator = Orchestrator()
