"""live/telemetry.py — Lightweight voice-pipeline timing instrumentation.

Non-blocking, in-memory per-session ring of (label, monotonic_ts) marks. Nothing
is written to disk and no extra I/O happens on the realtime audio path. Enable via
env MUSKU_LIVE_TELEMETRY=1; when enabled the live session emits a
`debug_telemetry` WS message per turn with derived deltas (TOTAL_TTFW etc.).

IDs/timestamps only — no user content is ever recorded here.
"""
from __future__ import annotations

import os
import time
from typing import Dict

ENABLED = bool(int(os.environ.get("MUSKU_LIVE_TELEMETRY", "0")))


class TurnTelemetry:
    """Per-turn timing collector. One instance per live session."""

    def __init__(self):
        self._marks: Dict[str, float] = {}

    def mark(self, label: str) -> None:
        if not ENABLED:
            return
        self._marks[label] = time.monotonic()

    def delta_ms(self, a: str, b: str):
        ta, tb = self._marks.get(a), self._marks.get(b)
        if ta is None or tb is None:
            return None
        return round((tb - ta) * 1000.0, 1)

    def report(self) -> Dict[str, object]:
        """Derived timings for one turn (or empty if disabled)."""
        if not ENABLED:
            return {}
        out: Dict[str, object] = {
            "ttfw_ms": self.delta_ms("MIC_CAPTURE", "GEMINI_FIRST_AUDIO"),
            "turn_total_ms": self.delta_ms("MIC_CAPTURE", "PLAYBACK_START"),
            "vad_to_first_audio_ms": self.delta_ms("VAD_TURN", "GEMINI_FIRST_AUDIO"),
        }
        return {k: v for k, v in out.items() if v is not None}

    def reset(self) -> None:
        self._marks.clear()
