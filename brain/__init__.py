# brain/__init__.py - Re-export shim.
# Brain ka single source of truth brain_core.py hai; ye package sirf
# legacy `from brain import ...` imports ko resolve karta hai (compat).
from brain_core import (
    MuskuBrain,
    deva_to_hinglish,
    has_pc_intent_hint,
    parse_pc_intent,
    parse_structured_app_intent,
    _gemini_chat,
    CONFIG_FILE,
    boss_instruction,
)
