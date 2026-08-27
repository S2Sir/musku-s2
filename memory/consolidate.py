# memory/consolidate.py — Deep cognitive recollection engine (MYRAA-style).
# Multi-turn dialogue + existing memories -> ADD/UPDATE/REMOVE transactions.
# Memory evolve hoti hai (sirf add nahi): galat/old fact update ya remove hoti hai.
from __future__ import annotations

import json
import re
import threading
import time

from . import paths, store

# Human-like + utility categories (consolidation engine inhe hi use karta hai).
CONSOLIDATE_CATEGORIES = (
    "relations", "places", "passion", "preferences",
    "emotional", "goal", "behavior",
    "finance", "ideas", "health", "learning", "tasks", "profile",
)

_consolidate_lock = threading.Lock()
_consolidating = False
_last_run_ts = 0.0
_MIN_INTERVAL = 30.0  # rate-limit: 30s me ek baar


def format_memory_context(max_per=40):
    """Current memories -> 'ID: xxx | Category: yyy | Fact: zzz' lines."""
    lines = []
    for category in CONSOLIDATE_CATEGORIES:
        file = paths.MEMORY_FILE_MAP.get(category)
        keyname = paths.MEMORY_KEY_NAMES.get(category, "items")
        if not file:
            continue
        for e in store.load_file(file, keyname)[-max_per:]:
            fact = (e.get("fact") if isinstance(e, dict) else str(e)).strip()
            if not fact:
                continue
            eid = str(e.get("id") or "") if isinstance(e, dict) else ""
            lines.append(f"ID: {eid} | Category: {category} | Fact: {fact}")
    return "\n".join(lines)


def process_conversation_slice(history):
    """Analyze dialogue slice -> apply ADD/UPDATE/REMOVE transactions.
    history = [{"role": "user"|"model", "text": "..."}].
    Returns applied transactions list ya None (nothing important/busy)."""
    global _consolidating, _last_run_ts
    with _consolidate_lock:
        if _consolidating:
            return None
        now = time.time()
        if now - _last_run_ts < _MIN_INTERVAL:
            return None
        _consolidating = True
        _last_run_ts = now
    try:
        if not history or len(history) < 2:
            return None
        dialogue = "\n".join(
            f"{'User' if h.get('role') == 'user' else 'Musku'}: {h.get('text')}"
            for h in history
            if h.get("text")
        )
        if not dialogue.strip():
            return None
        memory_ctx = format_memory_context()
        prompt = (
            "You are Musku's deep cognitive recollection engine. Analyze the recent conversation "
            "against previous persistent memories and output precise update transactions.\n\n"
            "### OBJECTIVE\n"
            "Decide if any statements contain durable, important personal facts, enduring preferences, "
            "aspirations, ongoing projects, critical relationships, key emotional milestones, or "
            "behavioral trends. Ignore small talk, greetings, chit-chat, or fleeting sentences "
            "(e.g. 'hello', 'how are you', 'lol').\n\n"
            "### CURRENT USER MEMORIES:\n"
            f"{memory_ctx or '(No memory records exist)'}\n\n"
            "### RECENT DIALOGUE SLICE:\n"
            f"{dialogue}\n\n"
            "### RULES\n"
            "- ACTIONS:\n"
            '  - "ADD": naya important info introduced (e.g. user says "My favorite food is lasagna" and not present).\n'
            '  - "UPDATE": pichhli info evolved/corrected (e.g. "I changed my major to computer science" jab memory "history" bole). Provide exact id.\n'
            '  - "REMOVE": info explicitly disproven ya user ne forget karne ko kaha. Provide exact id.\n'
            "- CATEGORY (one of): " + ", ".join(CONSOLIDATE_CATEGORIES) + "\n"
            "- TEXT STYLE: clean, concise, third-person declarative summaries "
            "(e.g. 'The user is building a startup.', 'The user loves playing GTA 6.'). "
            "No conversational filler, quotes, or timestamps.\n"
            "- ID: For ADD leave blank. For UPDATE/REMOVE provide the exact id from CURRENT USER MEMORIES.\n"
            'Return ONLY a JSON object: {"transactions": ['
            '{"action":"ADD|UPDATE|REMOVE","id":"","category":"...","text":"..."}]}'
        )
        from brain_core import _gemini_chat
        content = _gemini_chat(
            [{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0,
        )
        if not content:
            return None
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            return None
        data = json.loads(m.group(0))
        transactions = data.get("transactions") or []
        if not transactions:
            return None
        applied = store.apply_transactions(transactions)
        if applied:
            print(f"[Memory Consolidate] {len(applied)} updates applied.")
            return applied
        return None
    except Exception as e:
        print(f"[Memory Consolidate Error]: {e}")
        return None
    finally:
        with _consolidate_lock:
            _consolidating = False