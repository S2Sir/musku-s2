"""test_name_resolver.py — Unit tests for name extraction, persistence & greeting term."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import persona.name_resolver as nr


class TestExtractUserName(unittest.TestCase):
    def test_hinglish_mujhe_x_bulao(self):
        self.assertEqual(nr.extract_user_name("mujhe Rahul bulao"), "Rahul")
        self.assertEqual(nr.extract_user_name("mujhe Honey bulana"), "Honey")

    def test_mera_naam_x_hai(self):
        self.assertEqual(nr.extract_user_name("mera naam Rohit hai"), "Rohit")
        self.assertEqual(nr.extract_user_name("mera name Aman he"), "Aman")

    def test_my_name_is_x(self):
        self.assertEqual(nr.extract_user_name("my name is Sweetu"), "Sweetu")
        self.assertEqual(nr.extract_user_name("My name Karan"), "Karan")

    def test_call_me_x(self):
        self.assertEqual(nr.extract_user_name("call me Prince"), "Prince")

    def test_no_name(self):
        self.assertIsNone(nr.extract_user_name("aaj weather kaisa hai"))
        self.assertIsNone(nr.extract_user_name("mujhe paani lao"))

    def test_reserved_rejected(self):
        # "boss"/"aap" as extracted name must be ignored
        self.assertIsNone(nr.extract_user_name("mujhe boss bulao"))


class TestValidName(unittest.TestCase):
    def test_reserved(self):
        for r in ("boss", "bosss", "b0ss", "s2", "aap", "none", "sir"):
            self.assertFalse(nr._is_valid_name(r))

    def test_clean(self):
        for n in ("Rahul", "Rahul K.", "Sweetu", "J.J", "Aman99"):
            self.assertTrue(nr._is_valid_name(n))

    def test_too_long(self):
        self.assertFalse(nr._is_valid_name("x" * 31))


class TestPersistenceAndGreeting(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._cfg = os.path.join(self._tmp, "config.json")
        self._prof = os.path.join(self._tmp, "user_profile.json")
        nr.CONFIG_FILE = self._cfg
        nr.PROFILE_FILE = self._prof
        with open(self._cfg, "w", encoding="utf-8") as f:
            json.dump({"user_name": "S2", "language": "hinglish"}, f)

    def tearDown(self):
        nr.CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
        nr.PROFILE_FILE = os.path.join(BASE_DIR, "musku_data", "user_profile.json")

    def test_default_greeting_dear(self):
        self.assertEqual(nr.resolve_greeting_term(), "dear")

    def test_save_and_load_name(self):
        self.assertTrue(nr.save_user_name("Rahul"))
        self.assertEqual(nr.load_persisted_name(), "Rahul")
        self.assertEqual(nr.resolve_greeting_term(), "Rahul")

    def test_maybe_save_from_phrase(self):
        saved = nr.maybe_save_user_name("mujhe Rahul bulao")
        self.assertEqual(saved, "Rahul")
        self.assertEqual(nr.resolve_greeting_term(), "Rahul")

    def test_config_preserved(self):
        nr.save_user_name("Aman")
        with open(self._cfg, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["language"], "hinglish")  # other fields intact
        self.assertEqual(data["user_name"], "Aman")


if __name__ == "__main__":
    unittest.main()
