"""test_multitenant.py — Multi-tenant uid scoping, isolation & per-user config."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import tenant_ctx
import memory.paths as paths
from user_context import set_uid, get_uid, load_config, save_config, safe_uid
import persona.name_resolver as nr


class TestTenantCtx(unittest.TestCase):
    def tearDown(self):
        set_uid(None)

    def test_safe_uid(self):
        self.assertEqual(safe_uid(None), "owner")
        self.assertEqual(safe_uid("../evil"), "owner")
        self.assertEqual(safe_uid("alice"), "alice")
        self.assertEqual(safe_uid("a/b/c"), "owner")

    def test_set_get(self):
        set_uid("bob")
        self.assertEqual(get_uid(), "bob")
        set_uid(None)
        self.assertIsNone(get_uid())


class TestPathIsolation(unittest.TestCase):
    def tearDown(self):
        set_uid(None)

    def test_owner_uses_legacy(self):
        set_uid(None)
        self.assertTrue(paths.PROFILE_FILE.replace("\\", "/").endswith("musku_data/user_profile.json"))
        self.assertTrue(paths.DATA_DIR.replace("\\", "/").endswith("musku_data"))

    def test_per_user_isolated(self):
        set_uid("tenantA")
        self.assertIn("musku_users/tenantA/musku_data/user_profile.json",
                      paths.PROFILE_FILE.replace("\\", "/"))
        self.assertIn("musku_users/tenantA/musku_data/relations_memory.json",
                      paths.MEMORY_FILE_MAP["relations"].replace("\\", "/"))
        # different tenant -> different root
        set_uid("tenantB")
        self.assertIn("musku_users/tenantB", paths.DATA_DIR.replace("\\", "/"))
        # owner fallback still works
        set_uid(None)
        self.assertTrue(paths.DATA_DIR.endswith("musku_data"))


class TestPerUserConfig(unittest.TestCase):
    def setUp(self):
        self._uid = "tu_test_user"
        set_uid(self._uid)

    def tearDown(self):
        set_uid(None)
        d = os.path.join(BASE_DIR, "musku_users", self._uid)
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)

    def test_defaults_for_new_user(self):
        cfg = load_config(self._uid)
        self.assertEqual(cfg["relationship_mode"], "best_friend")
        self.assertEqual(cfg["language"], "hinglish")

    def test_save_and_load(self):
        save_config({"user_name": "Rahul", "language": "hindi"}, self._uid)
        cfg = load_config(self._uid)
        self.assertEqual(cfg["user_name"], "Rahul")
        self.assertEqual(cfg["language"], "hindi")


class TestPerUserNameResolver(unittest.TestCase):
    def setUp(self):
        self._uid = "tu_name_user"
        set_uid(self._uid)

    def tearDown(self):
        set_uid(None)
        d = os.path.join(BASE_DIR, "musku_users", self._uid)
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)

    def test_name_persists_per_user(self):
        saved = nr.maybe_save_user_name("mujhe Rahul bulao")
        self.assertEqual(saved, "Rahul")
        self.assertEqual(nr.resolve_greeting_term(), "Rahul")
        # another tenant still defaults to 'dear'
        set_uid("other_dude")
        self.assertEqual(nr.resolve_greeting_term(), "dear")
        set_uid(self._uid)
        self.assertEqual(nr.resolve_greeting_term(), "Rahul")


class TestLiveSessionRouting(unittest.TestCase):
    """Concurrent Live sessions: each uid routed to its OWN MuskuLiveSession."""

    def test_send_routes_to_correct_uid(self):
        import asyncio
        import live.browser_live_ws as m

        calls = []

        class FakeSess:
            active = True
            def __init__(self, name):
                self.name = name
            async def send_realtime_text(self, text):
                calls.append((self.name, "rt:" + text))
            async def send_client_text(self, text):
                calls.append((self.name, "cli:" + text))
            async def send_proactive_prompt(self, text):
                calls.append((self.name, "pro:" + text))
            async def send_greeting(self, script=None, force=False):
                calls.append((self.name, "greet"))
            async def update_system_prompt(self, p):
                calls.append((self.name, "sys:" + p))

        srv = m.BrowserLiveWSServer()
        a, b = FakeSess("A"), FakeSess("B")
        srv._sessions = {"A": a, "B": b}
        srv._last_uid = "A"
        srv._loop = object()  # truthy guard pass; fake ignores actual loop

        orig = asyncio.run_coroutine_threadsafe
        def fake(coro, loop):
            lp = asyncio.new_event_loop()
            try:
                lp.run_until_complete(coro)
            finally:
                lp.close()
            return None
        asyncio.run_coroutine_threadsafe = fake
        try:
            srv.send_realtime_text("hiA", uid="A")
            srv.send_realtime_text("hiB", uid="B")
            srv.send_client_text("yo", uid="B")
            srv.send_proactive_prompt_direct("p", uid="B")
            srv.send_start_greeting(uid="A")
            srv.send_start_greeting()          # no uid -> last session (A)
            srv.update_system_prompt("SYS", uid="B")
        finally:
            asyncio.run_coroutine_threadsafe = orig

        self.assertIn(("A", "rt:hiA"), calls)
        self.assertIn(("B", "rt:hiB"), calls)
        self.assertIn(("B", "cli:yo"), calls)
        self.assertIn(("B", "pro:p"), calls)
        self.assertIn(("A", "greet"), calls)
        self.assertIn(("A", "greet"), calls)  # send_start_greeting() w/o uid -> A
        self.assertIn(("B", "sys:SYS"), calls)
        # B's message must NOT reach A and vice-versa
        self.assertNotIn(("A", "rt:hiB"), calls)
        self.assertNotIn(("B", "rt:hiA"), calls)

    def test_disconnect_clears_session(self):
        import live.browser_live_ws as m
        srv = m.BrowserLiveWSServer()
        srv._sessions = {"U": object()}
        srv._last_uid = "U"
        with srv._lock:
            srv._sessions.pop("U", None)
            if srv._last_uid == "U":
                srv._last_uid = None
        self.assertEqual(srv._sessions, {})
        self.assertIsNone(srv._last_uid)


if __name__ == "__main__":
    unittest.main()
