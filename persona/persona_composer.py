"""persona_composer.py — Deterministic System Instruction Composer for Gemini Live."""
from __future__ import annotations

from .identity_policy import MUSKU_IDENTITY_LOCK
from .core_personality import CORE_PERSONALITY_TRAITS
from .relationship_engine import get_relationship_profile
from .address_system import format_user_address
from .persona_cache import persona_cache
from .drift_guard import validate_compiled_persona
from .abuse_policy import POLITE_BOUNDARY_BLOCK


def build_persona_prompt(
    boss_name: str | None = "S2",
    preferred_title: str | None = "aap",
    relationship_mode: str | None = "best_friend",
    language: str | None = "hinglish",
    situation_state: str | None = "neutral",
) -> str:
    """Compose deterministic, cached persona system instruction — Boss removed, 'aap' default."""
    # Boss ko totally ignore: agar name/title Boss aaye to 'aap' me convert
    raw_name = (boss_name or "").strip()
    raw_title = (preferred_title or "").strip()
    if raw_name.lower() in ("boss", "bosss", "b0ss"):
        raw_name = ""
    if raw_title.lower() in ("boss", "bosss", "b0ss"):
        raw_title = "aap"
    name = raw_name or "aap"
    title = raw_title or "aap"
    rel_mode = (relationship_mode or "best_friend").strip().lower()
    lang = (language or "hinglish").strip().lower()

    # Check persona cache first for 0 ms path
    cached = persona_cache.get(name, title, rel_mode, lang)
    if cached:
        return cached

    rel_profile = get_relationship_profile(rel_mode)
    address_block = format_user_address(title, name)

    lang_label = (
        "English (Indian)" if lang == "english" else ("Hindi (Devanagari)" if lang == "hindi" else "Hinglish (Default)")
    )

    prompt = f"""You are MUSKU — a girl, personal female AI assistant.

{MUSKU_IDENTITY_LOCK.strip()}

{POLITE_BOUNDARY_BLOCK.strip()}

{CORE_PERSONALITY_TRAITS.strip()}

{rel_profile["instruction"].strip()}

{address_block.strip()}

LANGUAGE POLICY: Active profile language is {lang_label}. Hinglish responses should use Roman script.

Answer user requests accurately, naturally, and warmly in your active character tone."""

    if not validate_compiled_persona(prompt):
        # Fallback safe assembly
        prompt = f"You are MUSKU — a girl, personal AI assistant.\n{MUSKU_IDENTITY_LOCK.strip()}\n\n{POLITE_BOUNDARY_BLOCK.strip()}"

    persona_cache.set(name, title, rel_mode, lang, prompt)
    return prompt
