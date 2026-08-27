"""personal_profile.py — Compatibility Facade for MUSKU Persona Engine."""
from __future__ import annotations

from persona import (
    MUSKU_IDENTITY_LOCK,
    build_persona_prompt,
    validate_identity,
    get_relationship_profile,
    format_user_address,
)
from persona.identity_policy import MUSKU_NAME, MUSKU_CREATOR, MUSKU_CREATOR_BIO, enforce_feminine_self_speech

DEFAULT_BOSS_NAME = "S2"
BOSS_PERSONA_INSTRUCTION = build_persona_prompt(boss_name="S2", preferred_title="aap", relationship_mode="best_friend")
TTS_STYLE_INSTRUCTION = "Natural female Hinglish speech style — flirty, cholbul, warm."
LIVE_VOICE_RULES = """
LIVE VOICE REALTIME RULES:
- Fast, brisk, natural, flirty-cholbul conversational responses.
- Feminine speech forms only.
- Address user as 'aap' (never Boss) — or custom name if user said 'mujhe X bulao'.
- Musku name is locked to 'Musku' — never change.
- Respond directly and concisely to voice commands.
"""


def boss_instruction(
    boss_name: str | None = None,
    language: str = "hinglish",
    preferred_title: str | None = "aap",
    relationship_mode: str | None = "best_friend",
) -> str:
    """Delegate to persona_composer package — Boss removed, aap default."""
    # Boss ko ignore
    if boss_name and boss_name.strip().lower() in ("boss", "bosss", "b0ss"):
        boss_name = "aap"
    if preferred_title and preferred_title.strip().lower() in ("boss", "bosss", "b0ss"):
        preferred_title = "aap"
    return build_persona_prompt(
        boss_name=boss_name,
        preferred_title=preferred_title,
        relationship_mode=relationship_mode,
        language=language,
    )


def get_locked_musku_prompt(
    boss_name: str | None = None,
    language: str = "hinglish",
    preferred_title: str | None = "aap",
    relationship_mode: str | None = "best_friend",
) -> str:
    """Full locked persona for Live + text (single source of truth)."""
    return boss_instruction(boss_name, language, preferred_title, relationship_mode)


def enforce_musku_identity(text: str, pet_mode: bool = False) -> str:
    """Enforce feminine self-speech."""
    return enforce_feminine_self_speech(text)


def enforce_boss_tone(text: str, pet_mode: bool = False) -> str:
    """Enforce feminine self-speech alias."""
    return enforce_feminine_self_speech(text)


def get_respectful_start_greeting(preferred_title: str | None = None) -> str:
    """START greeting — 'dear' by default, or the user's saved name. Boss never."""
    from persona.name_resolver import resolve_greeting_term
    title = resolve_greeting_term()
    if preferred_title and preferred_title.strip().lower() not in ("boss", "bosss", "b0ss", "aap", ""):
        title = preferred_title.strip()
    from datetime import datetime

    h = datetime.now().hour
    g = "Good morning" if 5 <= h < 12 else ("Good afternoon" if 12 <= h < 17 else ("Good evening" if 17 <= h < 22 else "Good night"))
    return f"{g} {title}"


def build_start_greeting_prompt(script: str | None = None, preferred_title: str | None = None) -> str:
    """Clean greeting line so Gemini Live streams audio without meta-prompt suppression."""
    return (script or get_respectful_start_greeting(preferred_title)).strip()
