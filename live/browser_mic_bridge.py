"""browser_mic_bridge.py - Browser mic -> MIC_CHUNK_RAW feed.

WebView getUserMedia (echoCancellation ON) se base64 PCM chunks aate hain;
yahan rebuffer karke native MicCapture jaisa FRAME_BYTES publish hota hai.

Musku: mic tabhi Gemini ko bhejo jab Live session ready ho (warna
SendLoop missing + chunks kho jaate hain). Prefetch buffer reconnect window.
"""
import base64
import struct
import threading
import time
from collections import deque

from realtime.event_bus import bus
from live import voice_config as cfg

_ACTIVE_TIMEOUT = 5.0
# ~3s @ 20ms frames — Gemini connect hone tak mic buffer
_MAX_PREFETCH = int(getattr(cfg, "MIC_PREFETCH_MAX", 150))


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


class BrowserMicBridge:
    """JS getUserMedia capture -> MIC_CHUNK_RAW (single authoritative feed)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._granted = False
        self._gemini_ready = False
        self._muted = False
        self._activity_gate = False
        self._last_chunk_t = 0.0
        self._last_speech_ms = 0.0
        self._buf = bytearray()
        self._prefetch = deque(maxlen=_MAX_PREFETCH)
        self._chunk_bytes = cfg.FRAME_BYTES  # 40ms chunks for balanced latency
        self._stats = {"chunks": 0, "dropped": 0, "prefetched": 0, "voice_chunks": 0, "noise_skipped": 0}
        self._rms_log_every = 100
        self._speech_active = False
        self._hangover = 0
        bus.subscribe("SESSION_CONNECTED", self._on_gemini_ready)
        bus.subscribe("SESSION_DISCONNECTED", self._on_gemini_lost)
        bus.subscribe("STATE_CHANGE", self._on_state_change)

    # --- Self-owned gate state (no live_client dependency) -----------------
    @property
    def muted(self) -> bool:
        with self._lock:
            return self._muted

    @property
    def activity_gate(self) -> bool:
        with self._lock:
            return self._activity_gate

    def set_muted(self, value: bool):
        with self._lock:
            self._muted = bool(value)

    def set_activity_gate(self, value: bool):
        with self._lock:
            self._activity_gate = bool(value)
            if self._activity_gate:
                self._prefetch.clear()

    def _on_gemini_ready(self, _payload=None):
        with self._lock:
            self._gemini_ready = True
            if not self._mic_forward_enabled():
                self._prefetch.clear()
                print("[BrowserMic] Gemini ready — mic muted, prefetch cleared")
                return
            pending = list(self._prefetch)
            self._prefetch.clear()
        for chunk in pending:
            bus.publish("MIC_CHUNK_RAW", chunk)
        if pending:
            print(f"[BrowserMic] Flushed {len(pending)} prefetched mic frames to Gemini")
        print("[BrowserMic] Gemini ready — mic feed open")

    def _on_gemini_lost(self, _payload=None):
        with self._lock:
            self._gemini_ready = False
            self._prefetch.clear()

    def _on_state_change(self, payload=None):
        st = str((payload or {}).get("new_state") or "")
        if st in ("reconnecting", "error", "connecting", "offline"):
            with self._lock:
                self._gemini_ready = False

    def is_granted(self) -> bool:
        with self._lock:
            return self._granted

    def is_active(self) -> bool:
        with self._lock:
            return self._granted and (time.time() - self._last_chunk_t) < _ACTIVE_TIMEOUT

    def on_granted(self):
        with self._lock:
            self._granted = True
        bus.publish("BROWSER_MIC_GRANTED")
        print("[BrowserMic] Permission granted — echo-cancel mic active")

    def on_denied(self, error: str = ""):
        with self._lock:
            self._granted = False
            self._buf.clear()
            self._prefetch.clear()
        bus.publish("BROWSER_MIC_DENIED", error or "denied")
        print(f"[BrowserMic] Permission denied: {error or 'denied'}")

    def _chunk_rms(self, chunk: bytes) -> float:
        n = len(chunk) // 2
        if n <= 0:
            return 0.0
        try:
            samples = struct.unpack(f"<{n}h", chunk[: n * 2])
            return (sum(s * s for s in samples) / n) ** 0.5 / 32768.0
        except Exception:
            return 0.0

    def _speech_thr(self) -> float:
        return float(getattr(cfg, "MIC_SPEECH_RMS", 0.034))

    def _track_speech(self, rms: float):
        """T0 marker — last mic chunk jisme real voice energy ho (perf-counter
        ms). Noise-gate threshold hi speech definition hai."""
        with self._lock:
            if rms >= self._speech_thr():
                self._last_speech_ms = _now_ms()

    def last_speech_ms(self) -> float:
        """Last speech mic chunk ka perf-counter ms (0.0 = koi speech nahi)."""
        with self._lock:
            return self._last_speech_ms

    def _should_send_chunk(self, rms: float) -> bool:
        """Background noise Gemini tak na jaye — sirf awaaz + thoda hangover."""
        if not cfg.MIC_NOISE_GATE_ENABLED:
            return True
        speech_thr = float(getattr(cfg, "MIC_SPEECH_RMS", 0.034))
        noise_floor = float(getattr(cfg, "MIC_NOISE_FLOOR", 0.018))
        hangover_max = int(getattr(cfg, "MIC_SPEECH_HANGOVER", 8))
        if rms >= speech_thr:
            self._speech_active = True
            self._hangover = hangover_max
            return True
        if self._speech_active and self._hangover > 0:
            self._hangover -= 1
            return True
        if rms < noise_floor:
            self._speech_active = False
            self._hangover = 0
            return False
        return self._speech_active

    def _mic_forward_enabled(self) -> bool:
        """START dabane tak Gemini ko mic mat bhejo (listen only when active)."""
        with self._lock:
            return not self._muted and not self._activity_gate

    def _apply_gain(self, chunk: bytes) -> bytes:
        gain = float(getattr(cfg, "MIC_INPUT_GAIN", 1.0))
        if gain <= 1.01:
            return chunk
        n = len(chunk) // 2
        if n <= 0:
            return chunk
        try:
            samples = struct.unpack(f"<{n}h", chunk[: n * 2])
            boosted = tuple(
                max(-32768, min(32767, int(s * gain))) for s in samples
            )
            return struct.pack(f"<{n}h", *boosted)
        except Exception:
            return chunk

    def on_meter_only(self, b64_pcm: str) -> bool:
        """Live WS mode — sirf mic gauge (Gemini forward alag /live se)."""
        if not b64_pcm:
            return False
        try:
            raw = base64.b64decode(b64_pcm, validate=True)
        except Exception:
            return False
        if len(raw) < 2:
            return False
        from live.mic_meter import publish_pcm_meter
        gain = float(getattr(cfg, "MIC_INPUT_GAIN", 1.0))
        publish_pcm_meter(raw, gain=gain)
        rms = self._chunk_rms(raw)
        self._track_speech(rms)
        with self._lock:
            self._last_chunk_t = time.time()
            if not self._granted:
                self._granted = True
        return True

    def _emit_chunk(self, chunk: bytes):
        chunk = self._apply_gain(chunk)
        from live.mic_meter import publish_pcm_meter
        publish_pcm_meter(chunk)
        # Ungated raw feed — local barge-in ke liye. Echo/activity gate ke
        # pehle publish hota hai taaki SPEAKING me bhi (gate ON) real user
        # speech local detector ko mile. Gemini ko nahi jata (gate block).
        bus.publish("MIC_CHUNK_RAW_UNGATED", chunk)
        if not self._mic_forward_enabled():
            return
        if not self._gemini_ready:
            self._prefetch.append(chunk)
            self._stats["prefetched"] += 1
            return
        rms = self._chunk_rms(chunk)
        self._track_speech(rms)
        if not cfg.MIC_NOISE_GATE_ENABLED:
            if rms > 0.015:
                self._stats["voice_chunks"] += 1
                if self._stats["voice_chunks"] in (1, 5, 25, 100):
                    print(f"[BrowserMic] Voice RMS={rms:.3f} (chunk #{self._stats['voice_chunks']})")
            bus.publish("MIC_CHUNK_RAW", chunk)
            return
        if not self._should_send_chunk(rms):
            self._stats["noise_skipped"] += 1
            return
        if rms > 0.015:
            self._stats["voice_chunks"] += 1
            if self._stats["voice_chunks"] in (1, 5, 25, 100):
                print(f"[BrowserMic] Voice RMS={rms:.3f} (chunk #{self._stats['voice_chunks']})")
        bus.publish("MIC_CHUNK_RAW", chunk)

    def on_chunk(self, b64_pcm: str) -> bool:
        if not b64_pcm:
            return False
        try:
            raw = base64.b64decode(b64_pcm, validate=True)
        except Exception:
            with self._lock:
                self._stats["dropped"] += 1
            return False
        if len(raw) < 2:
            return False

        pending = []
        with self._lock:
            if not self._granted:
                self._granted = True
            self._last_chunk_t = time.time()
            self._buf.extend(raw)
            while len(self._buf) >= self._chunk_bytes:
                chunk = bytes(self._buf[: self._chunk_bytes])
                del self._buf[: self._chunk_bytes]
                self._stats["chunks"] += 1
                pending.append(chunk)
        for chunk in pending:
            self._emit_chunk(chunk)
        with self._lock:
            if (
                getattr(cfg, "MIC_NOISE_GATE_ENABLED", False)
                and self._stats["chunks"] in (50, 200, 500)
            ):
                print(
                    f"[BrowserMic] Noise gate: {self._stats['noise_skipped']} skipped / "
                    f"{self._stats['chunks']} total"
                )
        return True

    def stats(self):
        with self._lock:
            return dict(self._stats)


browser_mic_bridge = BrowserMicBridge()


class BrowserMicStub:
    """Watchdog-compatible mic stand-in when PyAudio capture is disabled."""

    def __init__(self):
        self._running = threading.Event()

    def available(self):
        return True

    def start(self):
        self._running.set()
        return True

    def stop(self):
        self._running.clear()

    def health(self) -> bool:
        if not self._running.is_set():
            return False
        if not browser_mic_bridge.is_granted():
            return True
        return browser_mic_bridge.is_active()

    def set_muted(self, value: bool):
        browser_mic_bridge.set_muted(value)

    def set_activity_gate(self, value: bool):
        browser_mic_bridge.set_activity_gate(value)

    def stats(self):
        return browser_mic_bridge.stats()
