"""browser_audio_bridge.py - Browser speaker playback via Web Audio.

Gemini AI audio -> Web Audio (24kHz) in WebView so browser AEC can cancel
echo from Musku's voice while mic is also browser-captured.

PyAudio output is skipped when BROWSER_AUDIO_PLAYBACK is on.
"""
from __future__ import annotations

import base64
import threading
import time

from live import voice_config as cfg

_play_js = None  # set from main.py: lambda script: push_js(script)


def set_play_js(fn):
    global _play_js
    _play_js = fn


class BrowserAudioBridge:
    """Virtual speaker with drain/flush timing for voice_supervisor."""

    def __init__(self):
        self._lock = threading.Lock()
        self._play_end_t = 0.0
        self._bytes_sent = 0

    def play(self, pcm: bytes):
        if not pcm or not cfg.BROWSER_AUDIO_PLAYBACK:
            return
        b64 = base64.b64encode(pcm).decode("ascii")
        self.track_playback(len(pcm))
        if _play_js:
            _play_js(f"window.muskuPlayPcm && window.muskuPlayPcm('{b64}')")

    def track_playback(self, nbytes: int):
        duration = nbytes / float(cfg.OUTPUT_SAMPLE_RATE * cfg.INPUT_SAMPLE_WIDTH)
        with self._lock:
            now = time.time()
            self._play_end_t = max(self._play_end_t, now) + duration
            self._bytes_sent += nbytes

    def stop(self):
        with self._lock:
            self._play_end_t = 0.0
        if getattr(cfg, "BROWSER_LIVE_WS", False):
            return
        if _play_js:
            _play_js("window.muskuStopAudio && window.muskuStopAudio()")

    def drained(self) -> bool:
        with self._lock:
            return time.time() >= self._play_end_t - 0.04

    def flush(self, timeout: float = 2.0) -> bool:
        deadline = time.time() + max(0.1, float(timeout))
        while time.time() < deadline:
            if self.drained():
                return True
            time.sleep(0.04)
        return self.drained()


browser_audio_bridge = BrowserAudioBridge()


class BrowserSpeakerStub:
    """WS/browser playback — no PyAudio, no AI_AUDIO_CHUNK bus subscribe."""

    def __init__(self):
        self._running = threading.Event()

    def start(self):
        self._running.set()
        return True

    def close(self):
        self.stop()

    def stop(self):
        browser_audio_bridge.stop()

    def drained(self):
        return browser_audio_bridge.drained()

    def flush(self, timeout=None):
        from live import voice_config as cfg
        if timeout is None:
            timeout = cfg.TURN_FLUSH_TIMEOUT
        return browser_audio_bridge.flush(timeout)

    def health(self):
        return self._running.is_set()

    def recover(self):
        return "browser speaker ok"

    def watchdog_skip(self):
        return True

    def stats(self):
        return {"mode": "browser_ws"}
