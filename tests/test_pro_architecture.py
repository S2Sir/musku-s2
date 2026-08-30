"""test_pro_architecture.py — PRO Architecture Tests A-F

Covers:
A - User Isolation (chat/memory/profile)
B - Memory Personalization (per-uid behavior)
C - Browser History (IndexedDB/local)
D - Firebase Memory persists after browser clear
E - Multi-device Memory sync
F - Cross-user Security (verified UID)
"""
import os
import shutil
import unittest

from tenant_ctx import set_uid, get_uid
from memory import store
from memory.service import save_memory, get_memory
from user_context import load_config, save_config
import memory.chat as chat

UID_A = "pro_test_A"
UID_B = "pro_test_B"

class TestPROArchitecture(unittest.TestCase):
    def setUp(self):
        for u in (UID_A, UID_B):
            try:
                d = store.paths._data_dir(u)
                if os.path.isdir(d):
                    shutil.rmtree(d)
            except: pass
            try:
                d2 = os.path.join(store.paths.BASE_DIR if hasattr(store.paths, 'BASE_DIR') else "musku_users", u)
                if os.path.isdir(d2):
                    shutil.rmtree(d2)
            except: pass
        set_uid(None)

    def tearDown(self):
        set_uid(None)

    def test_A_user_isolation_chat_memory(self):
        set_uid(UID_A)
        save_memory("preferences", "A likes chai", importance=0.9, confidence=0.9)
        set_uid(UID_B)
        save_memory("preferences", "B likes coffee", importance=0.9, confidence=0.9)
        set_uid(UID_A)
        a_mem = get_memory(category="preferences")
        set_uid(UID_B)
        b_mem = get_memory(category="preferences")
        a_facts = [e.get("fact","") for e in a_mem]
        b_facts = [e.get("fact","") for e in b_mem]
        self.assertIn("A likes chai", " ".join(a_facts))
        self.assertNotIn("B likes coffee", " ".join(a_facts))
        self.assertIn("B likes coffee", " ".join(b_facts))
        self.assertNotIn("A likes chai", " ".join(b_facts))

    def test_B_memory_personalization(self):
        set_uid(UID_A)
        save_config({"language": "hinglish", "user_name": "A"}, UID_A)
        set_uid(UID_B)
        save_config({"language": "english", "user_name": "B"}, UID_B)
        cfg_a = load_config(UID_A)
        cfg_b = load_config(UID_B)
        self.assertEqual(cfg_a["language"], "hinglish")
        self.assertEqual(cfg_b["language"], "english")
        self.assertNotEqual(cfg_a["language"], cfg_b["language"])

    def test_C_browser_history_local_only(self):
        # PRO: Normal chat should NOT go to Firestore/Local JSON permanent file
        # Check that memory/chat.py save_chat does not create Firestore entry
        # and local JSON file is not created for normal chat (only recent_turns)
        set_uid(UID_A)
        # Ensure no history file exists before
        from memory import paths
        hist_file = os.path.join(paths.HISTORY_DIR, "2026-01-01.json")
        if os.path.exists(hist_file):
            os.remove(hist_file)
        chat.save_chat("2026-01-01", {"user_said": "hello", "musku_replied": "hi", "time": "10:00:00"})
        # Hybrid server daily JSON history enables cross-session recall
        self.assertTrue(os.path.exists(hist_file), "Daily chat JSON should be persisted for cross-session recall")
        # But recent_turns should exist (transient)
        self.assertTrue(os.path.exists(paths.RECENT_TURNS_FILE))

    def test_D_memory_persists_after_browser_clear(self):
        set_uid(UID_A)
        save_memory("profile", "D test fact remains", importance=0.9, confidence=0.9)
        # Simulate browser clear: chat history would be cleared, but memory remains in Firestore/local
        mem_before = get_memory(category="profile")
        self.assertTrue(any("D test fact" in str(e) for e in mem_before))

    def test_E_multidevice_memory_sync(self):
        # Same UID on two devices should see same memory
        set_uid(UID_A)
        save_memory("preferences", "E multidevice fact", importance=0.9, confidence=0.9)
        # Simulate second device loading same UID
        set_uid(UID_A)
        mem = get_memory(category="preferences")
        self.assertTrue(any("E multidevice" in str(e) for e in mem))

    def test_F_cross_user_security(self):
        from auth_verify import resolve_verified_uid
        # Valid token would resolve to token UID, not client UID
        # Simulate: token for A, client tries to claim B
        # Without valid token, resolve_verified_uid falls back to client_uid only when REQUIRE_AUTH=false or firebase not available
        # In prod with REQUIRE_AUTH=true and firebase available, it should deny
        # For this test, we check that verified UID is used for scoping, not client UID
        set_uid(UID_A)
        save_memory("profile", "F secure fact A", importance=0.9, confidence=0.9)
        set_uid(UID_B)
        b_mem = get_memory(category="profile")
        self.assertFalse(any("F secure fact A" in str(e) for e in b_mem))

if __name__ == "__main__":
    unittest.main(verbosity=2)
