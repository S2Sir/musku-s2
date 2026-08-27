"""address_system.py — Dynamic User Address & Title Management."""
from __future__ import annotations

VALID_TITLES = ["Sir", "Mamu", "Bestie", "Bro", "Jaan", "Yaar", "Dost", "Partner", "Girlfriend", "Custom"]


def format_user_address(preferred_title: str | None, user_name: str | None = None) -> str:
    """Generate system prompt instructions for dynamic user address — Boss fully removed, 'aap' is default."""
    title = (preferred_title or "").strip()
    name = (user_name or "").strip()
    # Boss ko totally remove: agar title/name Boss/S2 hai to ignore karke 'aap' use karo
    low_title = title.lower()
    low_name = name.lower()
    if title and low_title not in ("none", "user name", "name", "boss", "bosss", "b0ss"):
        active_address = title
    elif name and low_name not in ("boss", "bosss", "s2", "none", ""):
        active_address = name
    else:
        active_address = "aap"

    return f"""
=== USER ADDRESS INSTRUCTION (NO BOSS - USE 'aap') ===
- Primary User Address: "{active_address}" (default aap if no custom name).
- ALWAYS address user as "aap" respectfully — NEVER use "Boss/boss".
- If user said "mujhe X bulao" then use that X name, else "aap".
- NATURAL FREQUENCY CONTROL: Do NOT mechanically repeat "{active_address}" in every sentence.
  BAD: "{active_address}, aap kya kar rahe ho {active_address}?"
  GOOD: "Aapka project open hai. Kya main check karun?"
  OCCASIONAL: "Haan {active_address}, ye issue mil gaya."
- Address the user naturally, warmly, respectfully as "aap".
"""
