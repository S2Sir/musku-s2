"""
test_multitenant_isolation.py

Verifies TRUE multi-user isolation in MUSKU Web — the highest-priority security
requirement. Mirrors the prompt's Test A/B/C/D:

  Test A : User A name must NOT leak to User B
  Test B : User A preference must NOT leak to User B
  Test C : User A conversation must NOT leak to User B
  Test D : Session/state isolation (last reply, last user, conversation state,
           emotion mood, streak) must never cross users.

Run:  python -m unittest tests.test_multitenant_isolation -v
"""
import os
import shutil
import unittest

from tenant_ctx import set_uid, get_uid
from memory import turn_context, store, last_question
from brain import conversation, emotion


UID_A = "iso_test_user_A"
UID_B = "iso_test_user_B"


class TestMultiUserIsolation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Keep conversation state in-memory only for the test uids (no global
        # disable_disk() — that flag is process-wide and would corrupt other tests).
        for u in (UID_A, UID_B):
            conversation.memory_only(u)

    def setUp(self):
        # Start each test from a clean per-user state.
        conversation.reset(UID_A, keep_recent=False)
        conversation.reset(UID_B, keep_recent=False)
        turn_context._CACHE.pop(UID_A, None)
        turn_context._CACHE.pop(UID_B, None)
        # Clear any on-disk memory for these uids.
        for u in (UID_A, UID_B):
            try:
                d = store.paths._data_dir(u)
                if os.path.isdir(d):
                    shutil.rmtree(d)
            except Exception:
                pass

    def tearDown(self):
        # Never leak the in-process tenant context into other tests
        # (unittest doesn't run the pytest conftest reset).
        set_uid(None)
        for u in (UID_A, UID_B):
            conversation._STATES.pop(u, None)
            conversation._MEMORY_ONLY.discard(u)
            turn_context._CACHE.pop(u, None)

    # ------------------------------------------------------------------ #
    # Test A / B / C — memory layer isolation (profile, preferences, chat)
    # ------------------------------------------------------------------ #
    def _assert_isolated(self, category, fact_a, fact_b):
        set_uid(UID_A)
        store.save_memory(category, fact_a, source="test")
        set_uid(UID_B)
        store.save_memory(category, fact_b, source="test")

        set_uid(UID_A)
        a_card = store.format_live_memory_card()
        set_uid(UID_B)
        b_card = store.format_live_memory_card()

        self.assertIn(fact_a, a_card, "User A fact missing from A's memory card")
        self.assertNotIn(fact_b, a_card, "User B fact leaked into A's memory card")
        self.assertIn(fact_b, b_card, "User B fact missing from B's memory card")
        self.assertNotIn(fact_a, b_card, "User A fact leaked into B's memory card")

    def test_A_name_isolation(self):
        self._assert_isolated("profile", "Mera naam Rahul hai", "Mera naam Sam hai")

    def test_B_preference_isolation(self):
        self._assert_isolated("preferences", "Mujhe chai pasand hai", "Mujhe coffee pasand hai")

    def test_C_conversation_isolation(self):
        conversation.record_exchange("Hum kal project X ke baare mein baat kar rahe the", "Haan boss", uid=UID_A)
        conversation.record_exchange("Hum kal project Y ke baare mein baat kar rahe the", "Haan boss", uid=UID_B)

        rc_a = conversation.snapshot(UID_A).get("recent_context", [])
        rc_b = conversation.snapshot(UID_B).get("recent_context", [])
        joined_a = " ".join(e.get("user", "") for e in rc_a)
        joined_b = " ".join(e.get("user", "") for e in rc_b)
        self.assertIn("project X", joined_a)
        self.assertIn("project Y", joined_b)
        self.assertNotIn("project Y", joined_a)
        self.assertNotIn("project X", joined_b)

    # ------------------------------------------------------------------ #
    # Test D — runtime state isolation
    # ------------------------------------------------------------------ #
    def test_D_last_reply_isolation(self):
        turn_context.record_last_musku_reply("A ka last jawab", uid=UID_A)
        turn_context.record_last_musku_reply("B ka last jawab", uid=UID_B)
        self.assertEqual(last_question.get_last_reply(UID_A), "A ka last jawab")
        self.assertEqual(last_question.get_last_reply(UID_B), "B ka last jawab")
        self.assertNotEqual(
            last_question.get_last_reply(UID_A), last_question.get_last_reply(UID_B)
        )

    def test_D_last_user_isolation(self):
        turn_context.record_last_user_message("A user said", uid=UID_A)
        turn_context.record_last_user_message("B user said", uid=UID_B)
        self.assertEqual(turn_context.snapshot(UID_A)["last_user"], "A user said")
        self.assertEqual(turn_context.snapshot(UID_B)["last_user"], "B user said")

    def test_D_conversation_state_isolation(self):
        conversation.set_topic("Topic A", uid=UID_A)
        conversation.set_topic("Topic B", uid=UID_B)
        self.assertEqual(conversation.current_topic(UID_A), "Topic A")
        self.assertEqual(conversation.current_topic(UID_B), "Topic B")

        conversation.set_pending({"action": "doX"}, question="Q A?", uid=UID_A)
        conversation.set_pending({"action": "doY"}, question="Q B?", uid=UID_B)
        pa, qa = conversation.get_pending(UID_A)
        pb, qb = conversation.get_pending(UID_B)
        self.assertEqual(qa, "Q A?")
        self.assertEqual(qb, "Q B?")

    def test_D_emotion_mood_isolation(self):
        emotion.save_mood(None, "A trigger", "happy", 0.9, uid=UID_A)
        emotion.save_mood(None, "B trigger", "sad", 0.9, uid=UID_B)
        mood_a, _ = emotion.get_user_mood(None, uid=UID_A)
        mood_b, _ = emotion.get_user_mood(None, uid=UID_B)
        self.assertEqual(mood_a, "happy")
        self.assertEqual(mood_b, "sad")
        self.assertNotEqual(mood_a, mood_b)

    def test_D_streak_isolation(self):
        # User B's streak must remain untouched when User A's turn is processed.
        b_before = turn_context.snapshot(UID_B)["correct_streak"]
        # A turn 1: Musku asks a riddle -> awaiting answer
        turn_context.update_after_turn(
            "batao", "Boss ne ek paheli puchi: 1+1? Sahi jawab 2", uid=UID_A
        )
        # A turn 2: A answers correctly -> streak increments for A only
        turn_context.update_after_turn(
            "Sahi jawab", "Bahut sahi boss, genius!", uid=UID_A
        )
        self.assertEqual(turn_context.snapshot(UID_B)["correct_streak"], b_before)
        self.assertEqual(turn_context.snapshot(UID_A)["correct_streak"], 1)
        self.assertNotEqual(
            turn_context.snapshot(UID_A)["correct_streak"],
            turn_context.snapshot(UID_B)["correct_streak"],
        )

    # ------------------------------------------------------------------ #
    # Cross-user boundary: contextvar default must NOT collapse users
    # ------------------------------------------------------------------ #
    def test_contextvar_does_not_collapse_users(self):
        set_uid(UID_A)
        turn_context.record_last_musku_reply("from A via contextvar", uid=None)
        set_uid(UID_B)
        turn_context.record_last_musku_reply("from B via contextvar", uid=None)
        set_uid(UID_A)
        self.assertEqual(last_question.get_last_reply(), "from A via contextvar")
        set_uid(UID_B)
        self.assertEqual(last_question.get_last_reply(), "from B via contextvar")


if __name__ == "__main__":
    unittest.main(verbosity=2)
