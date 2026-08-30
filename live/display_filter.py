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


_JAPANESE_RE = re.compile(r"[\u3040-\u30FF\u4E00-\u9FFF\u3400-\u4DBF]")

def live_display_text(text: str) -> str:
    if not text:
        return text
    raw = str(text).strip()
    # Drop pure Japanese/Kana/Kanji noise (e.g. \"ある ある\") — Musku ko galat context mat bhejo
    if raw and _JAPANESE_RE.search(raw):
        # If majority is Japanese, drop entirely
        jp_chars = len(_JAPANESE_RE.findall(raw))
        if jp_chars >= 2 or jp_chars / max(1, len(raw)) > 0.3:
            return ""
    # Very short non-Latin non-Devanagari = likely garbled
    if raw and len(raw) < 3 and re.search(r"[^\x00-\x7F]", raw) and not re.search(r"[\u0900-\u097F]", raw):
        return ""
    out = deva_to_hinglish(raw)
    out = normalize_musku_name(out)
    out = enforce_musku_identity(out)
    for token in _WHITELIST:
        out = re.compile(re.escape(token), re.IGNORECASE).sub(token, out)
    # Final: if still Japanese after conversion, drop
    if out and _JAPANESE_RE.search(out):
        return ""
    return out.strip()
