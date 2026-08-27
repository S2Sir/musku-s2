# live/streak_praise.py — Correct-answer streak celebration (paheli/quiz).
#
# memory_bridge.save_chat_log me turn_context.claim_streak_celebration()
# milestone cross hone par RIDDLE_STREAK bus event publish karta hai.
# Ye helper us event ko active Live session me inject karta hai taaki
# Gemini khud (uski voice se) user ki tareef/praise bole.

import asyncio
import logging

logger = logging.getLogger("MUSKU.StreakPraise")

_PREFIX = (
    "[INTERNAL NOTE — sirf tumhare liye hai, ise user ko padhkar mat sunao, "
    "bas is par turant ACT karo]: "
)


def is_streak_note(text):
    """Gemini ka userTurn echo is note ko UI/user-said me na dikhaye."""
    return bool(text) and str(text).lstrip().startswith(_PREFIX)


def subscribe_streak(owner, session_getter, loop_getter):
    """RIDDLE_STREAK listener register karo.

    session_getter -> active Live session (ya None)
    loop_getter    -> us session ka running event loop
    """
    from realtime.event_bus import bus

    def _handler(payload=None):
        data = payload or {}
        instr = data.get("instruction") or ""
        if not instr:
            return
        loop = loop_getter() if callable(loop_getter) else loop_getter
        if not loop or not loop.is_running():
            return
        try:
            asyncio.run_coroutine_threadsafe(
                _inject(session_getter, instr), loop
            )
        except Exception as e:
            logger.debug("Streak praise schedule failed: %s", e)

    bus.subscribe("RIDDLE_STREAK", _handler)
    return _handler


async def _inject(session_getter, instruction):
    try:
        session = session_getter() if callable(session_getter) else session_getter
        if session is None:
            return
        from google.genai import types
        await session.send_client_content(
            turns=types.Content(
                role="user",
                parts=[types.Part(text=_PREFIX + instruction)],
            ),
            turn_complete=True,
        )
        logger.debug("Streak praise injected")
    except Exception as e:
        logger.debug("Streak praise inject failed: %s", e)
