# memory/turn_context.py — Last turn link: paheli/sawal ↔ user jawab match (persisted).
#
# MULTI-TENANT: state is strictly UID-scoped. Each user gets its own
# turn_context.json under their data dir and an in-memory cache entry. There is
# NO process-global turn state — User A's last reply can never leak to User B.
import json
import os
import re
import threading
from datetime import datetime

from . import paths
from tenant_ctx import safe_uid, get_uid

_LOCK = threading.RLock()
_CACHE = {}  # uid -> state dict (per-user in-memory cache)


def _state_file(uid=None):
    """Per-user turn-context file path (resolves under the user's data dir)."""
    return os.path.join(paths._data_dir(uid), "turn_context.json")

RIDDLE_HINTS = (
    "paheli", "pahali", "puzzle", "riddle", "quiz", "guess karo", "guess kro",
    "socho", "batao kya", "batao kaun", "dimag lagao", "try karo",
)
QUESTION_HINTS = (
    "?", "kya hai", "kaun hai", "kitne", "kahan", "kaise", "kyun", "kyon",
    "batao", "bataiye", "sunao", "puchhu", "pucho", "sawal",
)
EVAL_HINTS = (
    "sahi", "galat", "wrong", "correct", "shabash", "badhiya", "almost",
    "close", "nahi boss", "haan boss", "bilkul sahi", "thoda galat",
)
# Correct-answer streak (paheli/quiz) — user ke lagatar SAHI jawab.
_CORRECT_MARKERS = (
    "bilkul sahi", "sahi jawab", "sahi jawaab", "sahi kaha", "sahi bata",
    "bahut sahi", "shabash", "badhiya", "mast jawab", "correct", "perfect",
    "wow", "genius", "right hai", "aapne sahi", "haan bilkul",
)
_WRONG_MARKERS = (
    "galat", "wrong", "sahi nahi", "thoda galat", "nahi boss", "are nahi",
    "nahi nahi", "close", "almost", "galt",
)
# Jab streak in milestones par pahunche to ek baar praise/celebration.
_CELEBRATE_AT = (2, 3, 5, 8, 13)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _default_state():
    return {
        "last_user": "",
        "last_musku": "",
        "pending_question": None,
        "pending_type": None,
        "awaiting_answer": False,
        "last_evaluated": None,
        "correct_streak": 0,
        "streak_celebrated": 0,
        "updated_at": None,
    }


def _uid(uid):
    return safe_uid(uid if uid is not None else get_uid())


def _load(uid=None):
    u = _uid(uid)
    with _LOCK:
        if u in _CACHE:
            return _CACHE[u]
    data = None
    try:
        sf = _state_file(u)
        if os.path.exists(sf):
            with open(sf, "r", encoding="utf-8") as f:
                data = json.load(f)
    except Exception:
        data = None
    base = _default_state()
    if isinstance(data, dict):
        base.update(data)
    with _LOCK:
        _CACHE[u] = base
    return base


def _save(state, uid=None):
    u = _uid(uid)
    try:
        sf = _state_file(u)
        os.makedirs(os.path.dirname(sf), exist_ok=True)
        state["updated_at"] = _now()
        with open(sf, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        with _LOCK:
            _CACHE[u] = state
    except Exception as e:
        print(f"[TurnContext Save Error]: {e}")


def classify_musku_turn(text):
    """Musku ne paheli/sawal pucha ya nahi."""
    t = (text or "").strip()
    if not t:
        return None, None
    lower = t.lower()
    if any(h in lower for h in RIDDLE_HINTS):
        return "riddle", t[:800]
    if "?" in t or any(h in lower for h in QUESTION_HINTS):
        return "question", t[:800]
    return None, None


def _looks_like_evaluation(musku_reply):
    low = (musku_reply or "").lower()
    return any(m in low for m in EVAL_HINTS)


def _eval_is_wrong(musku_reply):
    low = (musku_reply or "").lower()
    return any(m in low for m in _WRONG_MARKERS)


def _eval_is_correct(musku_reply):
    low = (musku_reply or "").lower()
    return any(m in low for m in _CORRECT_MARKERS)


def _update_correct_streak(current, musku_reply):
    """Correct streak update: galat -> reset, sahi -> +1, ambiguous -> waisa hi."""
    if _eval_is_wrong(musku_reply):
        return 0
    if _eval_is_correct(musku_reply):
        return int(current) + 1
    return int(current)


def record_last_user_message(user_text, uid=None):
    """User jaise hi bolta hai (speech final), turant last_user save karo.
    Turn complete hone ka wait nahi — taaki bich me cut hua sawal bhi yaad rahe.
    Pending paheli/sawal state ko disturb nahi karta. Per-user scoped."""
    user_text = (user_text or "").strip()
    if not user_text:
        return
    with _LOCK:
        state = _load(uid)
        state["last_user"] = user_text[:500]
        _save(state, uid)


def record_last_musku_reply(reply, uid=None):
    """Musku ka last spoken reply save karo (complete ya interrupted/partial) —
    taaki 'ha batao' / 'aage batao' / 'continue karo' par wahi text verbatim
    repeat ho. Turn complete hone ka wait nahi karta — bich me ruka reply bhi
    yaad rahe. Per-user scoped."""
    reply = (reply or "").strip()
    if not reply:
        return
    with _LOCK:
        state = _load(uid)
        state["last_musku"] = reply[:800]
        _save(state, uid)


def update_after_turn(user_text, musku_reply, uid=None):
    """Har saved turn ke baad — pending paheli/sawal track karo. Per-user scoped."""
    user_text = (user_text or "").strip()
    musku_reply = (musku_reply or "").strip()
    if not user_text and not musku_reply:
        return

    with _LOCK:
        state = _load(uid)
        state["last_user"] = user_text[:500]
        state["last_musku"] = musku_reply[:800]

        ptype, ptext = classify_musku_turn(musku_reply)

        if ptype and ptext:
            state["pending_question"] = ptext
            state["pending_type"] = ptype
            state["awaiting_answer"] = True
        elif state.get("awaiting_answer") and user_text:
            if _looks_like_evaluation(musku_reply):
                state["last_evaluated"] = {
                    "question": state.get("pending_question") or "",
                    "type": state.get("pending_type") or "question",
                    "user_answer": user_text[:300],
                    "musku_eval": musku_reply[:400],
                }
                state["pending_question"] = None
                state["pending_type"] = None
                state["awaiting_answer"] = False
                state["correct_streak"] = _update_correct_streak(
                    state.get("correct_streak") or 0, musku_reply
                )
                if state["correct_streak"] == 0:
                    state["streak_celebrated"] = 0

        _save(state, uid)


def get_live_turn_context_block(uid=None):
    """Gemini Live prompt — user jawab ko last Musku sawal se link karo.
    Per-user scoped."""
    state = _load(uid)
    parts = []

    if state.get("awaiting_answer") and state.get("pending_question"):
        ptype = state.get("pending_type") or "question"
        parts.append(
            f"ACTIVE {ptype.upper()} — user ka agla message iska JAWAB ho sakta hai:\n"
            f"Musku ne abhi pucha: \"{state['pending_question']}\"\n"
            "ZAROORI: User jab jawab de, PEHLE isi sawal/paheli se match karke "
            "clearly bolo SAHI hai ya GALAT. Alag topic mat chhedo."
        )

    if state.get("last_musku"):
        parts.append(f"Musku ka LAST message: \"{state['last_musku']}\"")
    if state.get("last_user"):
        parts.append(f"User ka LAST message: \"{state['last_user']}\"")

    le = state.get("last_evaluated")
    if isinstance(le, dict) and le.get("question"):
        parts.append(
            "Pichhla evaluate hua: Musku ne pucha → user ne jawab diya → result mil chuka.\n"
            f"  Q: {le.get('question', '')[:220]}\n"
            f"  User jawab: {le.get('user_answer', '')[:120]}\n"
            f"  Result: {le.get('musku_eval', '')[:180]}"
        )

    if not parts:
        return ""

    header = (
        "IMMEDIATE CONVERSATION LINK (sabse important — user ka naya message "
        "aksar Musku ke LAST sawal/paheli ka jawab hota hai):\n"
    )
    rules = (
        "ANSWER-MATCH RULES:\n"
        "- User ne jawab diya ho to Musku ke pichhle message wale sawal/paheli se compare karo.\n"
        "- Paheli/quiz me clearly bolo: 'Sahi jawab boss!' ya 'Thoda galat boss — sahi jawab ... hai'.\n"
        "- Bina evaluate kiye naya sawal mat pucho jab user jawab de raha ho.\n"
        "- Last conversation hamesha yaad rakho — context mat todo."
    )
    return header + "\n".join(parts) + "\n\n" + rules


def snapshot(uid=None):
    with _LOCK:
        return dict(_load(uid))


def get_streak_prompt_block(uid=None):
    """Connect-time system prompt — sahi-jawab streak rule + current streak.
    Per-user scoped."""
    state = _load(uid)
    streak = int(state.get("correct_streak") or 0)
    line = ""
    if streak > 0:
        line = f"\nAbhi user ke {streak} paheli/sawal ke sahi jawab LAGATAR hain."
    return (
        "CORRECT-ANSWER STREAK RULE: Jab user paheli/sawal ka jawab de to "
        "PEHLE clearly bolo 'Sahi jawab!' ya 'Galat — sahi jawab ... hai'. "
        "Jab user lagatar 2-3 (ya zyada) sahi jawab de de, to BADE PYAAR se "
        "tareef/praise karo — jaise 'Aap to genius hain boss!' — thoda excited "
        "hokar. Galat jawab par streak reset hoti hai." + line
    )


def claim_streak_celebration(uid=None):
    """Milestone (2,3,5,8,13) cross hone par ek baar celebration instruction.
    Warna None. Live session isko inject karke Gemini se praise bolwata hai.
    Per-user scoped."""
    with _LOCK:
        state = _load(uid)
        streak = int(state.get("correct_streak") or 0)
        if streak < 2:
            return None
        if int(state.get("streak_celebrated") or 0) >= streak:
            return None
        state["streak_celebrated"] = streak
        _save(state)
        if streak == 2:
            msg = (
                f"User ne {streak} paheli/sawal LAGATAR sahi jawab diye hain. "
                f"Ab puraa pyaar se tareef karo — jaise 'Zabardast boss! {streak} "
                f"sahi jawab lagatar, aap to legend ho!' Phir agla sawal aage badhao."
            )
        elif streak == 3:
            msg = (
                f"User ne {streak} paheli/sawal LAGATAR sahi jawab diye hain. "
                f"Ab full excitement se genius wali tareef karo — jaise 'Aap to "
                f"genius hain boss! {streak} sahi jawab lagatar, kya baat hai!' "
                f"Phir agla sawal aage badhao."
            )
        else:
            msg = (
                f"User ne {streak} paheli/sawal LAGATAR sahi jawab diye hain — "
                f"naya record! Bade ghamand/tareef ke saath congratulate karo aur "
                f"agla sawal poochhne ke liye taiyar raho."
            )
        return {"streak": streak, "instruction": msg}
