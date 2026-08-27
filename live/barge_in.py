"""barge_in.py - Local barge-in while echo gate blocks mic-to-Gemini.

Default: disabled — mic always-on, Gemini server `interrupted`.
Enable with MUSKU_LOCAL_BARGE_IN=1 when MUSKU_ECHO_GATE=1.
"""

import logging
import threading
import time
from array import array

from realtime.event_bus import bus
from realtime.state_machine import SystemState
from live import voice_config as cfg

logger = logging.getLogger("MUSKU.BargeIn")

_BARGE_HITS_REQUIRED = 3
_BARGE_RMS_THRESHOLD = float(getattr(cfg, "BARGE_IN_RMS_THRESHOLD", 0.12))
_BARGE_COOLDOWN_S = 0.35


def _chunk_rms(chunk: bytes) -> float:
    n = len(chunk) // 2
    if n == 0:
        return 0.0
    try:
        vals = array("h")
        vals.frombytes(chunk)
        sq = sum(v * v for v in vals)
        rms = (sq / n) ** 0.5
        return min(1.0, rms / 5000.0)
    except Exception:
        return 0.0


class _NoOpBargeIn:
    """Stub when local barge-in disabled (server interrupt only)."""


class BargeInDetector:
    """Local user-speech detection during SPEAKING (echo-gate active only)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._speaking = False
        self._hits = 0
        self._last_trigger_t = 0.0
        self._enabled = bool(
            cfg.LOCAL_BARGE_IN_ENABLED and cfg.ECHO_GATE_WHILE_SPEAKING
        )
        if self._enabled:
            bus.subscribe("STATE_CHANGE", self._on_state_change)
            bus.subscribe("MIC_CHUNK_RAW_UNGATED", self._on_mic_chunk)

    def _on_state_change(self, payload=None):
        new_state = (payload or {}).get("new_state", "")
        with self._lock:
            self._speaking = new_state == SystemState.SPEAKING.value
            if not self._speaking:
                self._hits = 0

    def _on_mic_chunk(self, chunk):
        if not self._enabled:
            return
        with self._lock:
            if not self._speaking:
                return
            now = time.time()
            if now - self._last_trigger_t < _BARGE_COOLDOWN_S:
                return

        if _chunk_rms(chunk) < _BARGE_RMS_THRESHOLD:
            with self._lock:
                self._hits = 0
            return

        with self._lock:
            self._hits += 1
            if self._hits < _BARGE_HITS_REQUIRED:
                return
            self._hits = 0
            self._last_trigger_t = now

        logger.info("Local barge-in detected (user speech during SPEAKING)")
        bus.publish("INTERRUPT_RECEIVED", {"source": "local_barge"})


if cfg.LOCAL_BARGE_IN_ENABLED and cfg.ECHO_GATE_WHILE_SPEAKING:
    barge_in_detector = BargeInDetector()
else:
    barge_in_detector = _NoOpBargeIn()
