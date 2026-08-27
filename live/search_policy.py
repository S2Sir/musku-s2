"""Search mode — knowledge (Gemini) vs browser (Google tool).

Default: user info/search questions → Gemini jawab (no tool, no browser).
Sirf explicit "google pe / browser me search" → searchGoogle tool + Chrome.
"""
from __future__ import annotations

import re

_BROWSER_TARGETS = (
    "browser me",
    "browser pe",
    "browser par",
    "chrome me",
    "chrome pe",
    "google pe",
    "google me",
    "google par",
    "web pe",
    "web me",
    "internet pe",
    "internet me",
)
_SEARCH_VERBS = (
    "search",
    "dhundh",
    "dhundo",
    "dhoondh",
    "dhoondho",
    "khoj",
    "khojo",
)


def is_explicit_browser_search(text: str) -> bool:
    """User ne browser/Google pe search maanga — tool + Chrome tab."""
    t = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not t:
        return False
    if any(target in t for target in _BROWSER_TARGETS):
        return True
    if re.search(r"\bgoogle\s+(pe|me|par)\b", t) and any(v in t for v in _SEARCH_VERBS):
        return True
    if re.search(r"\b(browser|chrome|web|internet)\b", t) and any(v in t for v in _SEARCH_VERBS):
        return True
    return False


def build_browser_search_tool_output(query: str, tool_result: str) -> dict:
    """Mayra-style tool response — fast open + Gemini knowledge explain."""
    q = (query or "").strip()
    result = (tool_result or "").strip()
    try:
        from live.instant_search import get_profile_language
        lang = get_profile_language()
    except Exception:
        lang = "hinglish"

    if lang == "english":
        instruction = (
            "Browser search SUCCESS. Google opened in Chrome. Confirm search opened, then "
            "explain the topic in 2-4 sentences from your knowledge (pure English). "
            "Do NOT say sorry/fail. Do NOT ask what they want to know."
        )
    elif lang == "hindi":
        instruction = (
            "Browser search SUCCESS. Chrome me Google khul gaya. Pehle confirm karo, phir apni "
            "knowledge se 2-4 Devanagari sentences me samjhao. Sorry mat bolo."
        )
    else:
        instruction = (
            "Browser search SUCCESS. Chrome me Google khul gaya. Pehle short confirm: "
            "'Haan boss, maine Google pe search kar diya — browser me khul gaya.' "
            "Phir apni knowledge se 2-4 Roman Hinglish sentences me topic samjhao (aap + Boss). "
            "Scraped text mat padho — knowledge se explain karo. Sorry/gadbad mat bolo. "
            "'Kya jaanna chahte hain' mat puchho."
        )

    return {
        "status": "success",
        "query": q,
        "result": result,
        "instruction": instruction,
    }


def is_knowledge_search(text: str) -> bool:
    """Info question — Gemini knowledge se jawab, tool nahi."""
    t = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not t or is_explicit_browser_search(t):
        return False
    hints = (
        "search karke",
        "search kar ke",
        "ke baare me",
        "ke bare me",
        "kya karta",
        "kya karti",
        "kaun hai",
        "kya hai",
        "batao",
        "bataye",
        "samjhao",
        "explain",
        "tell me about",
        "who is",
        "what is",
    )
    if any(h in t for h in hints):
        return True
    if any(v in t for v in _SEARCH_VERBS) and not is_explicit_browser_search(t):
        return True
    return False
