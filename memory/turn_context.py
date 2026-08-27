# memory/turn_context.py — Last turn link: paheli/sawal ↔ user jawab match (persisted).
import json
import os
import re
import threading
from datetime import datetime

from . import paths

_LOCK = threading.Lock()
_STATE_FILE = os.path.join(paths.DATA_DIR, "turn_context.json")

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


def _load():
    try:
        if os.path.exists(_STATE_FILE):
            with open(_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                base = _default_state()
                base.update(data)
                return base
    except Exception:
        pass
    return _default_state()


def _save(state):
    try:
        os.makedirs(paths.DATA_DIR, exist_ok=True)
        state["updated_at"] = _now()
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
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


def record_last_user_message(user_text):
    """User jaise hi bolta hai (speech final), turant last_user save karo.
    Turn complete hone ka wait nahi — taaki bich me cut hua sawal bhi yaad rahe.
    Pending paheli/sawal state ko disturb nahi karta."""
    user_text = (user_text or "").strip()
    if not user_text:
        return
    with _LOCK:
        state = _load()
        state["last_user"] = user_text[:500]
        _save(state)


def record_last_musku_reply(reply):
    """Musku ka last spoken reply save karo (complete ya interrupted/partial) —
    taaki 'ha batao' / 'aage batao' / 'continue karo' par wahi text verbatim
    repeat ho. Turn complete hone ka wait nahi karta — bich me ruka reply bhi
    yaad rahe."""
    reply = (reply or "").strip()
    if not reply:
        return
    with _LOCK:
        state = _load()
        state["last_musku"] = reply[:800]
        _save(state)


def update_after_turn(user_text, musku_reply):
    """Har saved turn ke baad — pending paheli/sawal track karo."""
    user_text = (user_text or "").strip()
    musku_reply = (musku_reply or "").strip()
    if not user_text and not musku_reply:
        return

    with _LOCK:
        state = _load()
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

        _save(state)


def get_live_turn_context_block():
    """Gemini Live prompt — user jawab ko last Musku sawal se link karo."""
    state = _load()
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


def snapshot():
    with _LOCK:
        return dict(_load())


def get_streak_prompt_block():
    """Connect-time system prompt — sahi-jawab streak rule + current streak."""
    state = _load()
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


def claim_streak_celebration():
    """Milestone (2,3,5,8,13) cross hone par ek baar celebration instruction.
    Warna None. Live session isko inject karke Gemini se praise bolwata hai."""
    with _LOCK:
        state = _load()
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
