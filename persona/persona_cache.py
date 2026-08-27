"""persona_cache.py — SHA-256 Compiled Prompt Cache for MUSKU Persona."""
from __future__ import annotations

import hashlib
from typing import Dict, Any, Optional

from .persona_versioning import PERSONA_ENGINE_VERSION


class PersonaCache:
    """Zero-turn latency overhead prompt cache."""

    def __init__(self):
        self._cache: Dict[str, str] = {}
        self._hits = 0
        self._misses = 0

    def _make_key(self, user_name: str, preferred_title: str, relationship_mode: str, language: str) -> str:
        raw = f"{PERSONA_ENGINE_VERSION}:{user_name}:{preferred_title}:{relationship_mode}:{language}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, user_name: str, preferred_title: str, relationship_mode: str, language: str) -> Optional[str]:
        key = self._make_key(user_name, preferred_title, relationship_mode, language)
        if key in self._cache:
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        return None

    def set(self, user_name: str, preferred_title: str, relationship_mode: str, language: str, prompt: str):
        key = self._make_key(user_name, preferred_title, relationship_mode, language)
        self._cache[key] = prompt

    def clear(self):
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> Dict[str, Any]:
        return {"hits": self._hits, "misses": self._misses, "cached_entries": len(self._cache)}


persona_cache = PersonaCache()
