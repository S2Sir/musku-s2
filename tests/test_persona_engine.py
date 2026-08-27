"""test_persona_engine.py — Comprehensive Unit Test Suite for MUSKU 2.0 Persona Engine."""
from __future__ import annotations

import unittest
import sys
import os

# Add musku-2.0 to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from persona import (
    validate_identity,
    RELATIONSHIP_MODES,
    get_relationship_profile,
    format_user_address,
    build_persona_prompt,
    persona_cache,
    validate_compiled_persona,
)


class TestMuskuPersonaEngine(unittest.TestCase):

    def setUp(self):
        persona_cache.clear()

    def test_immutable_identity_policy(self):
        prompt = build_persona_prompt(boss_name="S2 Sir", preferred_title="Boss", relationship_mode="best_friend")
        self.assertTrue(validate_identity(prompt))
        self.assertTrue(validate_compiled_persona(prompt))
        self.assertIn("Musku", prompt)
        self.assertIn("S2 Sir", prompt)

    def test_relationship_modes(self):
        for mode_id in ["best_friend", "beti", "jigri", "caring", "girlfriend"]:
            profile = get_relationship_profile(mode_id)
            self.assertEqual(profile["id"], mode_id)
            prompt = build_persona_prompt(relationship_mode=mode_id)
            self.assertIn(profile["instruction"].strip(), prompt)

    def test_dynamic_user_address(self):
        titles = ["Boss", "Sir", "Mamu", "Bestie", "Bro", "Jaan", "Developer"]
        for title in titles:
            block = format_user_address(preferred_title=title, user_name="S2 Sir")
            self.assertIn(title, block)

    def test_persona_cache_hits_and_zero_turn_rebuild(self):
        # 1st call -> Cache Miss
        prompt1 = build_persona_prompt("S2 Sir", "Boss", "best_friend", "hinglish")
        stats1 = persona_cache.stats()
        self.assertEqual(stats1["misses"], 1)

        # 2nd call -> Cache Hit (0 ms overhead)
        prompt2 = build_persona_prompt("S2 Sir", "Boss", "best_friend", "hinglish")
        stats2 = persona_cache.stats()
        self.assertEqual(stats2["hits"], 1)
        self.assertEqual(prompt1, prompt2)


if __name__ == "__main__":
    unittest.main()
