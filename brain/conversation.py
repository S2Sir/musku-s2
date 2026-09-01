# conversation_state.py - Temporary conversation state (short-term, per-user).
#
# PHASE-3: Memory system long-term facts ke liye strong hai; ye module SHORT-TERM
# conversation/task state rakhta hai — current_topic, current_app, last_action,
# last_entity, pending_action/pending_question, task_state, recent context. Iska
# matlab Gemini ko har turn pura conversation repeat na karna pade (state hi
# context hai).
#
# MULTI-TENANT: state is strictly UID-scoped. Each user has its own in-memory
# state and its own conversation_state.json under their data dir. There is NO
# process-global conversation state — User A's topic/pending question can never
# leak into User B's context.
import json
import os
import threading
import time

from memory import paths
from tenant_ctx import safe_uid, get_uid

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_LOCK = threading.RLock()

# Disk write toggle — tests/checkup me False kar ke pure-memory mode (no side effects).
_WRITE_TO_DISK = True

# uid -> per-user state dict
_STATES = {}

# In-process test isolation: extra uids to keep in memory only (no disk)
_MEMORY_ONLY = set()


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _default_state():
    return {
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


def _uid(uid):
    return safe_uid(uid if uid is not None else get_uid())


def _state_file(uid):
    return os.path.join(paths._data_dir(uid), "conversation_state.json")


def _load(uid):
    u = _uid(uid)
    with _LOCK:
        if u in _STATES:
            return _STATES[u]
    data = None
    try:
        if _WRITE_TO_DISK and u not in _MEMORY_ONLY:
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
        _STATES[u] = base
    return base


def _persist(uid):
    if not _WRITE_TO_DISK:
        return
    u = _uid(uid)
    if u in _MEMORY_ONLY:
        return
    try:
        sf = _state_file(u)
        os.makedirs(os.path.dirname(sf), exist_ok=True)
        with _LOCK:
            state = _STATES.get(u, _default_state())
        with open(sf, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def disable_disk():
    """Pure-memory mode (tests/offline sandbox)."""
    global _WRITE_TO_DISK
    _WRITE_TO_DISK = False


def enable_disk():
    global _WRITE_TO_DISK
    _WRITE_TO_DISK = True


def memory_only(uid):
    """Force a uid to stay in-memory only (no disk) — used by tests."""
    _MEMORY_ONLY.add(_uid(uid))


def reset(uid=None, keep_recent=True):
    """Session state clear. keep_recent=True -> recent_context preserve.
    Per-user scoped."""
    u = _uid(uid)
    with _LOCK:
        cur = _STATES.get(u, _default_state())
        recent = (cur.get("recent_context") or []) if keep_recent else []
        state = _default_state()
        state["recent_context"] = recent
        state["updated_at"] = _now()
        _STATES[u] = state
        _persist(u)


def snapshot(uid=None):
    """Read-only copy (LLM context/prompt ke liye). Per-user scoped."""
    u = _uid(uid)
    with _LOCK:
        st = _STATES.get(u)
        if st is None:
            st = _load(u)
        snap = dict(st)
        snap["recent_context"] = [dict(e) for e in (st.get("recent_context") or [])]
        snap["task_state"] = dict(st.get("task_state") or {})
        pa = st.get("pending_action")
        if isinstance(pa, dict):
            snap["pending_action"] = dict(pa)
        return snap


# ---------------------------------------------------------------------------
# Topic / App / Action tracking
# ---------------------------------------------------------------------------
def set_topic(topic, uid=None):
    u = _uid(uid)
    with _LOCK:
        _load(u)["current_topic"] = str(topic or "").strip()[:200]
        _STATES[u]["updated_at"] = _now()
        _persist(u)


def set_app(app, uid=None):
    u = _uid(uid)
    with _LOCK:
        _load(u)["current_app"] = (app or "").strip().lower() or None
        _STATES[u]["updated_at"] = _now()


def set_action(action, app=None, entity=None, uid=None):
    """Successful controller action ke baad record (controller/router se)."""
    u = _uid(uid)
    with _LOCK:
        st = _load(u)
        st["last_action"] = (action or "").strip().lower()
        if app is not None:
            st["current_app"] = (app or "").strip().lower() or None
        if entity is not None:
            st["last_entity"] = str(entity).strip()[:200] or None
        if entity:
            st["current_topic"] = str(entity).strip()[:200]
        st["updated_at"] = _now()
        _persist(u)


def last_action(uid=None):
    with _LOCK:
        return _load(_uid(uid)).get("last_action")


def current_app(uid=None):
    with _LOCK:
        return _load(_uid(uid)).get("current_app")


def current_topic(uid=None):
    with _LOCK:
        return _load(_uid(uid)).get("current_topic") or ""


def record_exchange(user_text, reply=None, action=None, uid=None):
    """Recent_context (max 8) — LLM prompt ke liye halka context. Per-user scoped."""
    u = _uid(uid)
    with _LOCK:
        st = _load(u)
        ctx = st.get("recent_context") or []
        ctx.append({
            "user": str(user_text or "")[:200],
            "reply": str(reply or "")[:200],
            "action": action or st.get("last_action"),
            "t": _now(),
        })
        st["recent_context"] = ctx[-8:]
        st["updated_at"] = _now()
        _persist(u)


# ---------------------------------------------------------------------------
# Pending action / question (controller ne extra info maangi)
# ---------------------------------------------------------------------------
def clear_pending(uid=None):
    u = _uid(uid)
    with _LOCK:
        st = _load(u)
        st["pending_action"] = None
        st["pending_question"] = None
        st["updated_at"] = _now()
        _persist(u)


def set_pending(action_data, question=None, uid=None):
    """Controller ko extra detail chahiye (e.g. kya search karu, kis ko bheju)."""
    u = _uid(uid)
    with _LOCK:
        st = _load(u)
        st["pending_action"] = action_data
        st["pending_question"] = question or ""
        st["updated_at"] = _now()
        _persist(u)


def get_pending(uid=None):
    """Returns (action_data, question). None agar koi pending nahi."""
    with _LOCK:
        st = _load(_uid(uid))
        return st.get("pending_action"), st.get("pending_question") or ""


def has_pending(uid=None):
    with _LOCK:
        return _load(_uid(uid)).get("pending_action") is not None


# ---------------------------------------------------------------------------
# Task state (multi-step operations)
# ---------------------------------------------------------------------------
def set_task(key, value, uid=None):
    u = _uid(uid)
    with _LOCK:
        st = _load(u)
        ts = dict(st.get("task_state") or {})
        ts[str(key)] = value
        st["task_state"] = ts
        st["updated_at"] = _now()
        _persist(u)


def get_task(key, default=None, uid=None):
    with _LOCK:
        return (_load(_uid(uid)).get("task_state") or {}).get(key, default)

def get_context_string(uid=None):
    snap = snapshot(uid)
    parts = []
    if snap.get('current_topic'): parts.append(f"Current Topic: {snap['current_topic']}")
    if snap.get('current_app'): parts.append(f"Current App: {snap['current_app']}")
    if snap.get('last_action'): parts.append(f"Last Action: {snap['last_action']}")
    if snap.get('last_entity'): parts.append(f"Last Entity: {snap['last_entity']}")
    if not parts: return ''
    return 'CONVERSATION STATE (short-term - abhi joh app/baat chal rahi hai):\n' + '\n'.join(f'- {p}' for p in parts)

