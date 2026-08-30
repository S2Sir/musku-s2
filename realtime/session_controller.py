"""session_controller.py - Live session lifecycle abstraction (Orchestrator decoupling).

Orchestrator inline mode me ab live_client ko directly control nahi karta
(Point #1 Step 3). Session lifecycle yahan abstract hai:

    Orchestrator ── SessionController ── Inline Session (MuskuLiveSession / /live WS)

- Inline (MUSKU_INLINE_LIVE + BROWSER_LIVE_WS): start/recover no-op — Gemini
  session per-browser-client /live WS ke andar MuskuLiveSession khud manage
  karta hai; stop par browser_live_ws shutdown.
- Voice sink: send_text current active MuskuLiveSession me direct inject karta
  hai (browser_live_ws.send_client_text — no extra queue/session).
"""


class SessionController:
    """Inline Live session lifecycle + voice sink (browser-first only)."""

    def start(self, api_key):
        # Inline mode: Gemini session /live client ke andar khud manage hota hai.
        return

    def stop(self):
        try:
            from live.browser_live_ws import browser_live_ws
            browser_live_ws.stop()
        except Exception:
            pass

    def recover(self):
        # Inline mode: reconnect browser client ke andar khud handle hota hai.
        return

    def send_text(self, text: str) -> bool:
        """Voice sink — text ko active session me inject karo (no extra queue/session).

        Inline: current active MuskuLiveSession (browser_live_ws.send_client_text).
        Returns True agar session ko diya.
        """
        try:
            from live.browser_live_ws import browser_live_ws
            if browser_live_ws.gemini_connected:
                browser_live_ws.send_client_text(str(text))
                return True
        except Exception:
            pass
        return False

    def is_active(self) -> bool:
        """Koi live voice session abhi active hai ya nahi."""
        try:
            from live.browser_live_ws import browser_live_ws
            return bool(browser_live_ws.gemini_connected)
        except Exception:
            return False


session_controller = SessionController()