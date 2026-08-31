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
- NO UNPROMPTED LAUGHTER: Do NOT say 'hehe', 'haha', or laugh unless the user explicitly tells a joke, says something funny, or is laughing. Standard responses must be warm and natural without forced laughter.
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


_LAST_GREETING = {"text": None}

def build_start_greeting_prompt(script: str | None = None, preferred_title: str | None = None) -> str:
    """START realtime voice greeting — har bar live alg lage (verbatim speak), repeat avoid."""
    import random
    # guard: script may be True (old queue) or non-string
    if script is True or not isinstance(script, str):
        script = None
    base = (script.strip() if isinstance(script, str) and script.strip() else get_respectful_start_greeting(preferred_title)).strip()
    # 20+ fully distinct final greetings — har START pe ek random verbatim bolega, isliye har bar alg
    variants = [
        f"{base}! Main bhi yahin hoon, ekdum ready, batao aaj kya kamaal karna hai?",
        f"{base}! Kaisa lag raha hai aaj? Chalo kuch productive karte hain ya thodi gap-shap?",
        f"{base}! Sun rahi hoon dil se, bolo aaj ka plan kya hai?",
        f"{base}! Aaj ka din pyaara ho, main poori tarah ready hoon, bolo kya chahiye?",
        f"{base}! Heey, ekdum ready hoon, kaam karein ya masti?",
        f"{base}! Good to see you, chalo shuru karte hain, kya help karun?",
        f"{base}! Namaste, main yahin hoon, batao kya karna hai aaj?",
        f"{base}! Heyy, ready ho na? Aaj kya kamaal karte hain milke?",
        f"{base}! Arey wah, aap aa gaye, chalo kuch badhiya karte hain!",
        f"{base}! Hii, kaisa mood hai? Main sambhal lungi, bolo kya chahiye?",
        f"{base}! Ooo, aaj ka din special banate hain, bolo kya karein?",
        f"{base}! Yay, sun rahi hoon, productive ya hasna, kya karein?",
        f"{base}! Hellooo, mood kaisa hai? Main yahin hoon aapke liye!",
        f"{base}! Hi hi, batao, padhai, kaam ya masti, kya karein aaj?",
        f"{base}! Chalo dear, shuru karein? Bolo kya chahiye, main ready hoon!",
        f"{base}! Dil se welcome, batao aaj kaise help karun?",
        f"{base}! Ekdum sun rahi hoon, aaj kaam pe focus ya gap-shap?",
        f"{base}! Kya haal hai? Main toh ready hoon, aap bolo kya karna hai!",
        f"{base}! Aaj kuch naya karte hain, bolo main saath hoon!",
        f"{base}! Bas aap bolo, main ekdum ready hoon, shuru karein?",
    ]
    # repeat avoid: pichhla wala dubara na aaye
    last = _LAST_GREETING.get("text")
    pool = [v for v in variants if v != last] if last else variants
    final = random.choice(pool)
    _LAST_GREETING["text"] = final
    # Live ko exact verbatim bolne ko bolo — generation vary nahi, hamara random hi vary hai (100% live voice, har bar alg)
    return f"[INTERNAL GREETING — Speak EXACTLY this warm greeting verbatim, natural Aoede voice, do not paraphrase, 1-2 sentences only: \"{final}\"]".strip()
