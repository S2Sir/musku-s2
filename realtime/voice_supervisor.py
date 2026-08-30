"""voice_supervisor.py - Single authority for instant voice lifecycle.

All turn transitions flow through here (idempotent restore_listening).
Orchestrator wires I/O; VoiceSupervisor owns voice STATE + gate sync triggers.

Design goals:
- First audio ASAP (no wait for full response)
- LISTENING restore without unnecessary coupling to full speaker drain
- Duplicate restore_listening() calls are safe no-ops
- Milestone logging only (never per audio chunk)
"""

import logging
import threading
import time
from typing import Optional

from realtime.event_bus import bus
from realtime.state_machine import state_machine, SystemState
from realtime.turn_manager import turn_manager
from realtime.gate_controller import gate_controller as gate
from live import voice_config as cfg

logger = logging.getLogger("MUSKU.VoiceSupervisor")

# States where mic-to-Gemini feed is blocked (echo / no session)
_ACTIVITY_GATED_STATES = frozenset({
    SystemState.STARTING, SystemState.CONNECTING, SystemState.RECONNECTING,
    SystemState.RECOVERING, SystemState.ERROR,
} | ({SystemState.SPEAKING} if cfg.ECHO_GATE_WHILE_SPEAKING else set()))

_SPEAK_FROM_STATES = frozenset({
    SystemState.CONNECTED, SystemState.LISTENING,
    SystemState.THINKING, SystemState.INTERRUPTED, SystemState.TOOL_EXECUTING,
})

_THINK_FROM_STATES = frozenset({
    SystemState.CONNECTED, SystemState.LISTENING, SystemState.INTERRUPTED,
})

_STUCK_STATES = frozenset({
    SystemState.THINKING, SystemState.SPEAKING, SystemState.TOOL_EXECUTING,
})


def completion_ready(speaker, tm=None):
    """Playback + transcript flush check before turn archive."""
    if speaker is None:
        return True
    if not speaker.drained():
        return False
    if tm is not None:
        try:
            if getattr(tm, "_current_buffer", None):
                return False
        except Exception:
            pass
    return True


def _log_milestone(event: str, detail: str = ""):
    """Milestone-only log — hot path (MIC_CHUNK, AI_AUDIO per chunk) never here."""
    turn = turn_manager.get_current_turn()
    state = state_machine.current_state.value
    msg = f"[{turn}] {event} state={state}"
    if detail:
        msg = f"{msg} | {detail}"
    logger.info(msg)


class VoiceSupervisor:
    """Instant voice lifecycle — one source of truth for LISTENING restore."""

    def __init__(self):
        self._lock = threading.Lock()
        self._last_user_activity_t = 0.0
        self._last_ai_audio_t = 0.0
        self._first_audio_logged = False
        self._speaker = None

    def set_speaker(self, speaker):
        self._speaker = speaker

    def touch_user_activity(self):
        with self._lock:
            self._last_user_activity_t = time.time()

    def restore_listening(self, reason: str, force: bool = False) -> bool:
        """Idempotent LISTENING restore. Returns True if transition applied."""
        with self._lock:
            already = state_machine.current_state == SystemState.LISTENING
            if already and not force:
                return False
            turn_manager.complete_turn(reason=reason)
            state_machine.set_state(SystemState.LISTENING, context={"reason": reason})
            self._last_user_activity_t = time.time()
            self._first_audio_logged = False

        bus.publish("AUDIO_PLAYBACK_COMPLETE")
        _log_milestone("LISTENING_RESTORED", reason)
        return True

    def sync_activity_gate(self, new_state_value: str):
        """Apply echo gate from state change (called by orchestrator STATE_CHANGE)."""
        try:
            st = SystemState(new_state_value)
            gated = st in _ACTIVITY_GATED_STATES
            # LISTENING + live session = mic hamesha open (browser instant mode).
            if new_state_value.upper() == "LISTENING" and gate.is_connected():
                gated = False
            # Session up hone ke baad STARTING/CONNECTING dubara mic na roke (race fix).
            elif gated and gate.is_connected() and st in (
                SystemState.STARTING, SystemState.CONNECTING,
            ):
                gated = False
        except Exception:
            gated = new_state_value.upper() in {s.value for s in _ACTIVITY_GATED_STATES}
            if new_state_value.upper() == "LISTENING" and gate.is_connected():
                gated = False
        gate.set_activity_gate(gated)

    def on_session_connected(self, payload=None):
        reconnected = bool((payload or {}).get("reconnected"))
        turn_manager.new_turn()
        state_machine.set_state(
            SystemState.LISTENING,
            context={"reconnected": reconnected},
        )
        # Critical: unstuck gate after reconnect (SendLoop wired with gate=False too).
        gate.set_activity_gate(False)
        self.touch_user_activity()
        tag = "reconnected" if reconnected else "initial"
        _log_milestone("SESSION_CONNECTED", tag)

    def on_user_speech_final(self, text: str = ""):
        turn_manager.new_turn()
        self._first_audio_logged = False
        if state_machine.current_state in _THINK_FROM_STATES:
            state_machine.set_state(SystemState.THINKING)
        self.touch_user_activity()
        preview = (str(text)[:60] + "...") if len(str(text)) > 60 else str(text)
        _log_milestone("USER_SPEECH_FINAL", preview)

    def on_user_speech_partial(self, text: str = ""):
        """User abhi bol raha hai — LISTENING hi rakho (THINKING mat dalo, feel slow hota hai)."""
        if not text:
            return
        if state_machine.current_state in (
            SystemState.CONNECTED, SystemState.LISTENING, SystemState.INTERRUPTED,
        ):
            state_machine.set_state(SystemState.LISTENING)
        self.touch_user_activity()

    def on_ai_audio_chunk(self):
        """Hot path — minimal work. First chunk only logs milestone."""
        if state_machine.current_state in _SPEAK_FROM_STATES:
            state_machine.set_state(SystemState.SPEAKING)
        with self._lock:
            self._last_ai_audio_t = time.time()
            first = not self._first_audio_logged
            if first:
                self._first_audio_logged = True
        if first:
            _log_milestone("FIRST_AI_AUDIO")

    def on_interrupt(self, speaker=None):
        turn_manager.interrupt_turn()
        turn_manager.new_turn()
        spk = speaker or self._speaker
        if spk is not None:
            try:
                spk.stop()
            except Exception:
                pass
        state_machine.set_state(SystemState.INTERRUPTED)
        self.restore_listening("interrupt", force=True)

    def on_fast_route_complete(self, success: bool = True):
        self.restore_listening(
            "fast_route_complete" if success else "fast_route_failed"
        )

    def on_turn_complete(self, speaker=None, transcript_manager=None):
        """TURN_COMPLETE — instant mode: LISTENING turant; flush background me."""
        _log_milestone("TURN_COMPLETE")

        if getattr(cfg, "INSTANT_LISTEN_RESTORE", False):
            self.restore_listening("turn_complete_instant")

            def _bg_flush():
                spk = speaker or self._speaker
                if spk is None:
                    return
                try:
                    spk.flush(timeout=cfg.TURN_FLUSH_TIMEOUT)
                except Exception:
                    pass

            threading.Thread(target=_bg_flush, daemon=True, name="TurnFlush").start()
            return

        def _bg():
            spk = speaker or self._speaker
            timeout = cfg.TURN_FLUSH_TIMEOUT
            if spk is not None:
                try:
                    spk.flush(timeout=timeout)
                except Exception:
                    pass
            self.restore_listening("turn_complete")

        threading.Thread(target=_bg, daemon=True, name="TurnFlush").start()

    def check_stuck(self) -> bool:
        """Ultimate fallback only — normal path is turn_complete / interrupt."""
        # Mic gate kabhi LISTENING par stuck na rahe (voice Gemini tak na jaye).
        if gate.is_connected() and state_machine.current_state == SystemState.LISTENING:
            try:
                if gate.is_gate_engaged():
                    logger.warning("Gate stuck ON while LISTENING — forcing mic open")
                    gate.set_activity_gate(False)
            except Exception:
                pass

        state = state_machine.current_state
        if state not in _STUCK_STATES:
            return False

        now = time.time()
        with self._lock:
            user_idle = now - self._last_user_activity_t
            ai_idle = now - self._last_ai_audio_t

        timeout = (
            cfg.VOICE_STUCK_TIMEOUT_SPEAKING if state == SystemState.SPEAKING
            else cfg.VOICE_STUCK_TIMEOUT
        )
        idle_for = ai_idle if state == SystemState.SPEAKING else user_idle
        if idle_for > timeout:
            logger.warning(
                f"Gate-stuck fallback: {state.value} silent {idle_for:.1f}s"
            )
            return self.restore_listening("gate_stuck_recovered")
        return False


voice_supervisor = VoiceSupervisor()
