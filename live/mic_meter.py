# live/mic_meter.py — Mic RMS for UI gauges (headset/browser path).
import struct

from realtime.event_bus import bus


def pcm_rms(pcm: bytes) -> float:
    n = len(pcm) // 2
    if n <= 0:
        return 0.0
    try:
        samples = struct.unpack(f"<{n}h", pcm[: n * 2])
        return min(1.0, (sum(s * s for s in samples) / n) ** 0.5 / 32768.0)
    except Exception:
        return 0.0


def publish_pcm_meter(pcm: bytes, gain: float = 1.0):
    """Mic gauge ke liye RMS — Gemini forward se alag."""
    if not pcm:
        return
    rms = pcm_rms(pcm)
    if gain > 1.01:
        rms = min(1.0, rms * gain)
    bus.publish("MIC_METER", {"rms": rms})
