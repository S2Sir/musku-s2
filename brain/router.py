"""brain/router.py — Pure Conversational Intent Router for MUSKU 2.0.

Classifies incoming user text into purely conversational intents:
- 'greeting': Morning/evening/hello greetings
- 'question': Direct questions or inquiry
- 'explanation': Requests for detailed explanations or help
- 'follow_up': Follow-up prompts ('haan batao', 'aage bolo')
- 'memory_query': Queries about user's stored memories or profile
- 'emotional_chat': Mood, feelings, emotional expression
- 'web_search': Requests for live web search / current news / weather
- 'conversation': General conversational dialogue (default)

MUST NOT classify or route any OS, PC, browser, application, or system control actions.
"""
from __future__ import annotations

import re


def classify_conversational_intent(text: str) -> str:
    """Classifies user input into purely conversational categories."""
    if not text or not isinstance(text, str):
        return "conversation"

    txt = text.strip().lower()

    # Greetings
    if re.search(r"\b(hi|hello|hey|good morning|good evening|good afternoon|namaste|kya haal|salam)\b", txt):
        return "greeting"

    # Follow-up continuations
    if re.search(r"\b(ha+n?|aage|aur batao|phir kya hua|batao|batan?a)\b", txt) and len(txt) < 30:
        return "follow_up"

    # Memory / Profile queries
    if re.search(r"\b(mera naam|mujhe kya pasand|meri profile|yaad hai|kya yaad|tumhe pata hai)\b", txt):
        return "memory_query"

    # Web search / live info requests
    if re.search(r"\b(search|google|news|samachar|aaj ka weather|weather|mausam|latest)\b", txt):
        return "web_search"

    # Direct questions
    if re.search(r"\b(kya|kaise|kyo|kabar|kab|kahan|kaun|kon|wh|what|how|why|when|where|who)\b|\?", txt):
        return "question"

    # Emotional conversation
    if re.search(r"\b(udaas|happy|sad|stressed|khush|pareshan|love|dost|feeling)\b", txt):
        return "emotional_chat"

    return "conversation"


def is_fast_pc_command(text: str) -> bool:
    """Legacy compatibility guard. Returns False unconditionally for all inputs.
    Musku 2.0 does NOT execute any PC or computer-control commands.
    """
    return False
