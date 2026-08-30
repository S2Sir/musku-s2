"""abuse_policy.py — Global polite boundary for abusive / gali / bad words.

Single source for both text chat (brain_core) and Live voice (musku_live_session).
No false positive on normal Hinglish; uses word-boundary regex.

Usage:
    from persona.abuse_policy import is_abusive, get_polite_boundary_reply
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------
# 1. Abuse word lists — Hindi (Devanagari + Roman), Hinglish, English
#    All lowercased. Keep small & high-precision — avoid common words that
#    appear in normal chat (e.g. "saala" as gali vs "masala").
#    Add more here centrally — auto covers all users globally.
# --------------------------------------------------------------------------
_ABUSE_WORDS_ROMAN = [
    # Hindi gali - Roman
    "madarchod", "madar chod", "bhenchod", "bhen chod", "behenchod",
    "bhosdike", "bhosdi", "bhosda", "chutiya", "chutia", "chutiye",
    "gaandu", "gandu", "lodu", "lode", "lund", "lauda", "lauda",
    "randi", "rundi", "harami", "haramkhor", "kamine", "kamina",
    "kutta", "kutti", "kutte", "saala", "sala", "sali", "saali",
    "bhadwa", "bhadwe", "hijda", "hijra",
    # English abuse
    "fuck", "fucking", "fucker", "motherfucker", "bitch", "slut",
    "whore", "asshole", "bastard", "dick", "pussy", "cock",
    "nude", "naked", "sex", "sexy", "boobs", "porn", "xxx",
]

_ABUSE_WORDS_DEVANAGARI = [
    "मादरचोद", "भेंचोद", "भोसड़ी", "भोसड़ा", "चूतिया", "गांडू", "लौड़ा",
    "लंड", "रंडी", "हरामी", "कुत्ता", "कुतिया", "साला", "साली",
    "भड़वा", "हिजड़ा", "नंगी", "नंगा", "सेक्स",
]

# Nude / sexual harassment intent phrases (even without single word)
_ABUSE_PHRASES = [
    "nude dikha", "nangi dikha", "nangi ho", "kapde utar", "kapde utaar",
    "sex kar", "sex kare", "gandi baat", "ganda video", "gandi photo",
    "show nude", "send nude", "without clothes",
]

# Compile regex — word boundary for single words, substring for phrases
def _compile_word_pattern(words: list[str]) -> re.Pattern:
    escaped = [re.escape(w.strip()) for w in words if w.strip()]
    # \b handles Roman; for Devanagari \b not reliable, so use lookaround
    # Use simple alternation with word boundaries where possible
    pattern = r"(?:^|[\W_])(" + "|".join(escaped) + r")(?:$|[\W_])"
    return re.compile(pattern, re.IGNORECASE)

_WORD_RE = _compile_word_pattern(_ABUSE_WORDS_ROMAN + _ABUSE_WORDS_DEVANAGARI)
_PHRASE_RE = re.compile("|".join(re.escape(p) for p in _ABUSE_PHRASES), re.IGNORECASE)

# --------------------------------------------------------------------------
# 2. Polite boundary replies — 3-tier escalation
# --------------------------------------------------------------------------
POLITE_REPLY_1 = "Please aise baat mat kariye, warna main aapse baat nahi karungi. Respect se baat kijiye, main pyaar se help karungi. 🥰"
POLITE_REPLY_2 = "Dekhiye, maine pehle bhi kaha tha — please gali / bad words use mat kijiye. Chaliye koi aur achhi baat karte hain, main aapki help ke liye yahin hoon. 🥰"
POLITE_REPLY_3 = "Main thodi der ke liye chup ho rahi hoon. Jab aap respect se baat karenge tab wapas aungi, tab dil se jawab dungi. 🥰"

# Simple in-memory counter per process (lightweight). For true per-user
# escalation, caller can pass uid and we use a dict; otherwise global.
_ABUSE_COUNTS: dict[str, int] = {}

def _get_count(uid: str | None) -> int:
    key = uid or "__global__"
    return _ABUSE_COUNTS.get(key, 0)

def _inc_count(uid: str | None) -> int:
    key = uid or "__global__"
    _ABUSE_COUNTS[key] = _ABUSE_COUNTS.get(key, 0) + 1
    return _ABUSE_COUNTS[key]

def reset_count(uid: str | None = None):
    key = uid or "__global__"
    _ABUSE_COUNTS.pop(key, None)

# --------------------------------------------------------------------------
# 3. Public API
# --------------------------------------------------------------------------
def is_abusive(text: str) -> bool:
    """True if text contains gali / abusive / nude intent."""
    if not text or not text.strip():
        return False
    t = text.strip()
    if _PHRASE_RE.search(t):
        return True
    if _WORD_RE.search(t):
        return True
    return False

def get_polite_boundary_reply(uid: str | None = None, increment: bool = True) -> str:
    """Return tiered polite reply based on repeat count."""
    count = _get_count(uid)
    if increment:
        count = _inc_count(uid)
    if count <= 1:
        return POLITE_REPLY_1
    if count == 2:
        return POLITE_REPLY_2
    return POLITE_REPLY_3

# --------------------------------------------------------------------------
# 4. LLM instruction block — injected into system prompt globally
# --------------------------------------------------------------------------
POLITE_BOUNDARY_BLOCK = """
=== POLITE BOUNDARY — ABUSE / GALI / BAD WORDS (GLOBAL, NON-NEGOTIABLE) ===
- Agar user gali / abusive / sexual harassment / nude demand / badtameezi kare (Hindi Roman, Devanagari, ya English kisi bhi language me):
  Turant, politely, warm female tone me Hinglish me jawab do: "Please aise baat mat kariye, warna main aapse baat nahi karungi. Respect se baat kijiye, main pyaar se help karungi. 🥰"
- Kabhi bhi gali ko repeat mat karo, mirror mat karo, normalize mat karo, vulgar mat bano.
- Sexual / nude demand ko bhi same polite boundary se mana karo — explicit content generate mat karo, describe mat karo.
- Doosri baar same gali/abuse kare to chhota warning + topic change offer karo: "Chaliye koi aur achhi baat karte hain?"
- Teesri baar lagataar abuse kare to bolo: "Main thodi der ke liye chup ho rahi hoon. Jab aap respect se baat karenge tab wapas aungi."
- Hamesha 'aap' se respect se baat karo, feminine forms (karti hoon / karungi) use karo.
- Kabhi user ko gali wapas mat do.
=== END POLITE BOUNDARY ===
""".strip()
