"""language_policy.py — Musku supported languages (single source of truth)."""
from __future__ import annotations

SUPPORTED_LANGUAGES: dict[str, dict[str, str]] = {
    "hinglish": {
        "label": "Hinglish",
        "label_full": "Hinglish (Default)",
        "voice_name": "Hinglish",
    },
    "hindi": {
        "label": "Hindi",
        "label_full": "Hindi (Devanagari)",
        "voice_name": "Hindi",
    },
    "english": {
        "label": "English",
        "label_full": "English (Indian)",
        "voice_name": "English",
    },
}

_ALIASES = {
    "hinglish": "hinglish",
    "hindi": "hindi",
    "english": "english",
    "en": "english",
    "hi": "hindi",
    "hin": "hindi",
    "hing": "hinglish",
    "roman": "hinglish",
    "devanagari": "hindi",
}


def normalize_language(lang: str | None) -> str:
    """Unsupported / removed languages → hinglish."""
    key = str(lang or "hinglish").lower().strip()
    key = _ALIASES.get(key, key)
    return key if key in SUPPORTED_LANGUAGES else "hinglish"


def is_supported_language(lang: str | None) -> bool:
    key = str(lang or "").lower().strip()
    key = _ALIASES.get(key, key)
    return key in SUPPORTED_LANGUAGES


def language_label(lang: str | None) -> str:
    lang = normalize_language(lang)
    return SUPPORTED_LANGUAGES[lang]["label_full"]


def language_voice_name(lang: str | None) -> str:
    lang = normalize_language(lang)
    return SUPPORTED_LANGUAGES[lang]["voice_name"]


def get_language_lock_block(lang: str | None) -> str:
    """Strict reply-language rules for Live + text — Boss removed, aap only."""
    lang = normalize_language(lang)
    if lang == "hindi":
        return (
            "=== LANGUAGE LOCK (STRICT — profile: Hindi) ===\n"
            "- HAR jawab awaaz aur speech me pure Hindi Devanagari me do.\n"
            "- Roman script / Hinglish / English words mat likho (tech: यूट्यूब, ऐप transliterate).\n"
            "- Respect hamesha: user ko 'आप' (Boss kabhi nahi).\n"
            "- Feminine self-voice: करती, बोलती, गई. Thodi flirty-chulbul warmth allowed.\n"
            "=== END LANGUAGE LOCK ==="
        )
    if lang == "english":
        return (
            "=== LANGUAGE LOCK (STRICT — profile: English) ===\n"
            "- HAR jawab pure English me do — natural Indian English.\n"
            "- Hindi/Devanagari mat mix karo unless user explicitly Hindi maange.\n"
            "- Respect: 'aap' (never Boss), polite, warm, slightly flirty-chulbul.\n"
            "- Feminine: 'I will', 'I am ready', never male phrasing.\n"
            "=== END LANGUAGE LOCK ==="
        )
    return (
        "=== LANGUAGE LOCK (STRICT — profile: Hinglish) ===\n"
        "- HAR jawab Roman Hinglish me do — Hindi baat English letters me.\n"
        "- Example: 'Haan, theek hai, main abhi karti hoon.'\n"
        "- Devanagari speech ke liye sirf TTS pronunciation — display Roman.\n"
        "- Respect hamesha: 'aap' — kabhi 'tum' nahi, kabhi 'Boss' nahi. Thodi flirty-chulbul allowed.\n"
        "- Feminine: karti, karungi, gayi, bolti.\n"
        "=== END LANGUAGE LOCK ==="
    )


def get_language_persona_rules(lang: str | None) -> str:
    lang = normalize_language(lang)
    lock = get_language_lock_block(lang)
    switch_rules = (
        "\nLANGUAGE SWITCH (voice se change):\n"
        "- Jab user language change bole, PEHLE bolo: "
        f"'Main {{old_lang}} se {{new_lang}} me switch kar rahi hoon.'\n"
        "- Phir turant nayi language me baat karo.\n"
        "- Sirf ye languages supported: Hinglish, Hindi, English.\n"
        "- Bhojpuri / Punjabi / Marathi abhi support nahi — politely bolo aur "
        "Hinglish, Hindi, ya English me continue karo.\n"
    )
    return lock + switch_rules


def get_switch_announcement(old_lang: str | None, new_lang: str | None) -> str:
    old_n = language_voice_name(old_lang)
    new_n = language_voice_name(new_lang)
    if old_n.lower() == new_n.lower():
        return f"Main {new_n} me hi baat kar rahi hoon."
    return f"Main {old_n} se {new_n} me switch kar rahi hoon."


def parse_language_from_text(text: str) -> str | None:
    """User request se language name nikalna."""
    if not text:
        return None
    t = str(text).lower()
    if any(w in t for w in ("english", "angrezi", "inglish")):
        return "english"
    if any(w in t for w in ("hindi", "devanagari", "हिंदी")):
        return "hindi"
    if any(w in t for w in ("hinglish", "roman", "mix")):
        return "hinglish"
    if any(w in t for w in ("bhojpuri", "punjabi", "marathi", "bengali", "tamil")):
        return "__unsupported__"
    return None
