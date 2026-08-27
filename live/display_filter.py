"""Roman Hinglish filter for Live chat bubbles.

Gemini voice/TTS Devanagari me bol sakti hai (pronunciation ke liye).
Chat bubble me sirf Roman Hinglish dikhna chahiye — yahan convert hota hai.
"""
import re

from brain_core import deva_to_hinglish
from personal_profile import enforce_musku_identity

_WHITELIST = (
    "hello", "hi", "good morning", "good evening", "boss",
    "open", "close", "delete", "edit", "save", "cancel",
    "start", "stop", "run", "search", "type",
)

# STT / speech often mishears "Musku" — normalize for display + saved history.
_MUSKU_NAME_ALIASES = (
    "moscow", "musco", "musko", "muskoo", "muskuu", "muska", "musky",
    "masku", "musca", "muskow", "muskou", "muskhu", "muskuh",
    "myraa", "myra", "mayra", "mayraa", "miraa", "mira",
    "musku",  # lowercase -> Musku
)
_MUSKU_ALIAS_RES = [
    re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE)
    for alias in _MUSKU_NAME_ALIASES
]


def normalize_musku_name(text: str) -> str:
    """User Musku ko galat suna/speech-to-text typo — chat me 'Musku' dikhao."""
    if not text:
        return text
    out = str(text)
    for rx in _MUSKU_ALIAS_RES:
        out = rx.sub("Musku", out)
    return out


def live_display_text(text: str) -> str:
    if not text:
        return text
    out = deva_to_hinglish(str(text))
    out = normalize_musku_name(out)
    out = enforce_musku_identity(out)
    for token in _WHITELIST:
        out = re.compile(re.escape(token), re.IGNORECASE).sub(token, out)
    return out
