# conversation_state.py - Temporary conversation state (short-term, per-session).
#
# PHASE-3: Memory system long-term facts ke liye strong hai; ye module SHORT-TERM
# conversation/task state rakhta hai — current_topic, current_app, last_action,
# last_entity, pending_action/pending_question, task_state, recent context. Iska
# matlab Gemini ko har turn pura conversation repeat na karna pade (state hi
# context hai). In-memory + light JSON persistence (musku_data/conversation_state.json).
import json
import os
import threading
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(BASE_DIR, "musku_data")
_STATE_FILE = os.path.join(_DATA_DIR, "conversation_state.json")

_LOCK = threading.Lock()

# Disk write toggle — tests/checkup me False kar ke pure-memory mode (no side effects).
_WRITE_TO_DISK = True

_state = {
    "current_topic": "",
    "current_app": None,
    "last_action": None,
    "last_entity": None,
    "pending_action": None,
    "pending_question": None,
    "recent_context": [],   # list of compact recent exchanges (max 8)
    "task_state": {},
    "updated_at": None,
}


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _persist():
    if not _WRITE_TO_DISK:
        return
    try:
        os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(_state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def disable_disk():
    """Pure-memory mode (tests/offline sandbox)."""
    global _WRITE_TO_DISK
    _WRITE_TO_DISK = False


def enable_disk():
    global _WRITE_TO_DISK
    _WRITE_TO_DISK = True


def reset(keep_recent=True):
    """Session state clear. keep_recent=True -> recent_context preserve."""
    with _LOCK:
        recent = (_state.get("recent_context") or []) if keep_recent else []
        _state.clear()
        _state.update({
            "current_topic": "",
            "current_app": None,
            "last_action": None,
            "last_entity": None,
            "pending_action": None,
            "pending_question": None,
            "recent_context": recent,
            "task_state": {},
            "updated_at": _now(),
        })
        _persist()


def snapshot():
    """Read-only copy (LLM context/prompt ke liye)."""
    with _LOCK:
        snap = dict(_state)
        snap["recent_context"] = [dict(e) for e in (_state.get("recent_context") or [])]
        snap["task_state"] = dict(_state.get("task_state") or {})
        pa = _state.get("pending_action")
        if isinstance(pa, dict):
            snap["pending_action"] = dict(pa)
        return snap


# ---------------------------------------------------------------------------
# Topic / App / Action tracking
# ---------------------------------------------------------------------------
def set_topic(topic):
    with _LOCK:
        _state["current_topic"] = str(topic or "").strip()[:200]
        _state["updated_at"] = _now()
        _persist()


def set_app(app):
    with _LOCK:
        _state["current_app"] = (app or "").strip().lower() or None
        _state["updated_at"] = _now()


def set_action(action, app=None, entity=None):
    """Successful controller action ke baad record (controller/router se)."""
    with _LOCK:
        _state["last_action"] = (action or "").strip().lower()
        if app is not None:
            _state["current_app"] = (app or "").strip().lower() or None
        if entity is not None:
            _state["last_entity"] = str(entity).strip()[:200] or None
        if entity:
            _state["current_topic"] = str(entity).strip()[:200]
        _state["updated_at"] = _now()
        _persist()


def last_action():
    with _LOCK:
        return _state.get("last_action")


def current_app():
    with _LOCK:
        return _state.get("current_app")


def current_topic():
    with _LOCK:
        return _state.get("current_topic") or ""


def record_exchange(user_text, reply=None, action=None):
    """Recent_context (max 8) — LLM prompt ke liye halka context."""
    with _LOCK:
        ctx = _state.get("recent_context") or []
        ctx.append({
            "user": str(user_text or "")[:200],
            "reply": str(reply or "")[:200],
            "action": action or _state.get("last_action"),
            "t": _now(),
        })
        _state["recent_context"] = ctx[-8:]
        _state["updated_at"] = _now()
        _persist()


# ---------------------------------------------------------------------------
# Pending action / question (controller ne extra info maangi)
# ---------------------------------------------------------------------------
def clear_pending():
    with _LOCK:
        _state["pending_action"] = None
        _state["pending_question"] = None
        _state["updated_at"] = _now()
        _persist()


def set_pending(action_data, question=None):
    """Controller ko extra detail chahiye (e.g. kya search karu, kis ko bheju)."""
    with _LOCK:
        _state["pending_action"] = action_data
        _state["pending_question"] = question or ""
        _state["updated_at"] = _now()
        _persist()


def get_pending():
    """Returns (action_data, question). None agar koi pending nahi."""
    with _LOCK:
        return _state.get("pending_action"), _state.get("pending_question") or ""


def has_pending():
    with _LOCK:
        return _state.get("pending_action") is not None


# ---------------------------------------------------------------------------
# Task state (multi-step operations)
# ---------------------------------------------------------------------------
def set_task(key, value):
    with _LOCK:
        ts = dict(_state.get("task_state") or {})
        ts[str(key)] = value
        _state["task_state"] = ts
        _state["updated_at"] = _now()
        _persist()


def get_task(key, default=None):
    with _LOCK:
        return (_state.get("task_state") or {}).get(key, default)

def get_context_string():
    snap = snapshot()
    parts = []
    if snap.get('current_topic'): parts.append(f"Current Topic: {snap['current_topic']}")
    if snap.get('current_app'): parts.append(f"Current App: {snap['current_app']}")
    if snap.get('last_action'): parts.append(f"Last Action: {snap['last_action']}")
    if snap.get('last_entity'): parts.append(f"Last Entity: {snap['last_entity']}")
    if not parts: return ''
    return 'CONVERSATION STATE (short-term - abhi joh app/baat chal rahi hai):\n' + '\n'.join(f'- {p}' for p in parts)

