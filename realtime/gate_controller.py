"""gate_controller.py - Mic feed gate abstraction (VoiceSupervisor decoupling).

VoiceSupervisor ab LiveClient ke baare me nahi jaanta (Point #1 Step 2).
Ye controller mic-feed gate ko ek interface ke peeche abstract karta hai:

    VoiceSupervisor ── GateController ── InlineGate (BrowserMicBridge, browser-first)

- set_activity_gate(value)  : echo/activity gate ON/OFF (BrowserMicBridge write)
- is_connected()            : Gemini Live session connected hai ya nahi
                              (browser_live_ws.gemini_connected — inline)
- is_gate_engaged()         : gate abhi ON hai ya nahi (stuck-detection)
"""

from live import voice_config as cfg


class InlineGate:
    """Primary mic path: BrowserMicBridge (WebView / inline live)."""

    def __init__(self):
        self._bridge = None

    def _bridge_obj(self):
        if self._bridge is None:
            try:
                from live.browser_mic_bridge import browser_mic_bridge
                self._bridge = browser_mic_bridge
            except Exception:
                self._bridge = False
        return self._bridge or None

    def set_activity_gate(self, value: bool):
        b = self._bridge_obj()
        if b is not None:
            try:
                b.set_activity_gate(bool(value))
            except Exception:
                pass

    def is_gate_engaged(self) -> bool:
        b = self._bridge_obj()
        if b is not None:
            try:
                return bool(b.activity_gate)
            except Exception:
                return False
        return False


class GateController:
    """Dispatch gate ops to browser mic path (inline primary)."""

    def __init__(self):
        self.inline = InlineGate()

    def set_activity_gate(self, value: bool):
        value = bool(value)
        if getattr(cfg, "BROWSER_MIC_ENABLED", False):
            self.inline.set_activity_gate(value)

    def is_connected(self) -> bool:
        """Gemini Live session connected (inline /live)."""
        try:
            from live.browser_live_ws import browser_live_ws
            return bool(browser_live_ws.gemini_connected)
        except Exception:
            return False

    def is_gate_engaged(self) -> bool:
        if getattr(cfg, "BROWSER_MIC_ENABLED", False):
            return self.inline.is_gate_engaged()
        return False


gate_controller = GateController()