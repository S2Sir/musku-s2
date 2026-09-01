# memory/paths.py - Memory/chat storage paths (MULTI-TENANT aware).
#
# All path symbols (PROFILE_FILE, DATA_DIR, MEMORY_FILE_MAP, ...) now resolve to
# the CURRENT user's isolated storage via a contextvar (see user_context.set_uid).
# When no uid is set (legacy local "owner" user) the original global paths are
# returned, so the existing single-user behaviour is fully preserved.
import os
import re
import threading

from tenant_ctx import safe_uid, get_uid, set_uid  # single shared tenant ctx

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USERS_ROOT = os.path.join(BASE_DIR, "musku_users")
LEGACY_DATA_DIR = os.path.join(BASE_DIR, "musku_data")
LEGACY_HISTORY_DIR = os.path.join(BASE_DIR, "musku_chat")

# Global lock shared across all users (file I/O safety).
LOCK = threading.Lock()

# uid-independent constants
CONTEXT_WINDOW = 20
MEMORY_MAX_PER_CATEGORY = 60
# History recall window for "last time" queries — real human like
HISTORY_RECALL_WINDOW = 30

# category -> storage key inside its file (uid-independent)
MEMORY_KEY_NAMES = {
    "relations": "relations",
    "places": "places",
    "passion": "passion",
    "preferences": "preferences",
    "pc_command": "commands",
    "finance": "finance",
    "ideas": "ideas",
    "health": "health",
    "inventory": "inventory",
    "learning": "learning",
    "tasks": "tasks",
    "emotional": "emotional",
    "goal": "goal",
    "behavior": "behavior",
    "profile": "important_facts",
}

# category -> filename (relative to the user's musku_data dir)
_CAT_FILENAMES = {
    "relations": "relations_memory.json",
    "places": "places_memory.json",
    "passion": "passion_memory.json",
    "preferences": "preferences_memory.json",
    "pc_command": "pc_command_memory.json",
    "finance": "finance_memory.json",
    "ideas": "ideas_memory.json",
    "health": "health_memory.json",
    "inventory": "inventory_memory.json",
    "learning": "learning_memory.json",
    "tasks": "tasks_memory.json",
    "emotional": "emotional_memory.json",
    "goal": "goal_memory.json",
    "behavior": "behavior_memory.json",
    "profile": "user_profile.json",
    "": "user_profile.json",
}

# Other legacy filenames
_LEGACY = {
    "DATA_DIR": LEGACY_DATA_DIR,
    "HISTORY_DIR": LEGACY_HISTORY_DIR,
    "PROFILE_FILE": os.path.join(LEGACY_DATA_DIR, "user_profile.json"),
    "RULES_FILE": os.path.join(LEGACY_DATA_DIR, "rules_config.json"),
    "SUMMARY_FILE": os.path.join(BASE_DIR, "chat_summary.txt"),
    "RECENT_TURNS_FILE": os.path.join(LEGACY_DATA_DIR, "recent_turns.json"),
    "RELATIONS_FILE": os.path.join(LEGACY_DATA_DIR, "relations_memory.json"),
    "PLACES_FILE": os.path.join(LEGACY_DATA_DIR, "places_memory.json"),
    "PASSION_FILE": os.path.join(LEGACY_DATA_DIR, "passion_memory.json"),
    "PREFERENCES_FILE": os.path.join(LEGACY_DATA_DIR, "preferences_memory.json"),
    "PC_MEMORY_FILE": os.path.join(LEGACY_DATA_DIR, "pc_command_memory.json"),
    "FINANCE_FILE": os.path.join(LEGACY_DATA_DIR, "finance_memory.json"),
    "IDEAS_FILE": os.path.join(LEGACY_DATA_DIR, "ideas_memory.json"),
    "HEALTH_FILE": os.path.join(LEGACY_DATA_DIR, "health_memory.json"),
    "INVENTORY_FILE": os.path.join(LEGACY_DATA_DIR, "inventory_memory.json"),
    "LEARNING_FILE": os.path.join(LEGACY_DATA_DIR, "learning_memory.json"),
    "TASKS_FILE": os.path.join(LEGACY_DATA_DIR, "tasks_memory.json"),
    "EMOTIONAL_FILE": os.path.join(LEGACY_DATA_DIR, "emotional_memory.json"),
    "GOAL_FILE": os.path.join(LEGACY_DATA_DIR, "goal_memory.json"),
    "BEHAVIOR_FILE": os.path.join(LEGACY_DATA_DIR, "behavior_memory.json"),
    "MEMORY_INDEX_FILE": os.path.join(LEGACY_DATA_DIR, "memory_index.json"),
    "REMINDERS_FILE": os.path.join(LEGACY_DATA_DIR, "reminders.json"),
}

_DYNAMIC = set(_LEGACY.keys())


# --------------------------------------------------------------------------- #
# uid resolution (delegates to tenant_ctx — single shared contextvar)
# --------------------------------------------------------------------------- #
_recent_cache: dict = {}  # uid -> cache dict (for RECENT_CONTEXT_CACHE)


def _safe_uid(uid) -> str:
    return safe_uid(uid)


def _current_uid() -> str:
    return safe_uid(get_uid())


def _root(uid=None) -> str:
    u = safe_uid(uid if uid is not None else get_uid())
    if u == "owner":
        return BASE_DIR
    return os.path.join(USERS_ROOT, u)


def _data_dir(uid=None) -> str:
    u = safe_uid(uid if uid is not None else get_uid())
    if u == "owner":
        return LEGACY_DATA_DIR
    return os.path.join(_root(u), "musku_data")


def _hist_dir(uid=None) -> str:
    u = safe_uid(uid if uid is not None else get_uid())
    if u == "owner":
        return LEGACY_HISTORY_DIR
    return os.path.join(_root(u), "musku_chat")


def _category_file(category, uid=None) -> str:
    fn = _CAT_FILENAMES.get(category, "user_profile.json")
    return os.path.join(_data_dir(uid), fn)


# --------------------------------------------------------------------------- #
# live proxies (stable objects so `from import` keeps them live per uid)
# --------------------------------------------------------------------------- #
class _LiveFileMap:
    """MEMORY_FILE_MAP replacement — resolves category -> current-uid file path."""

    def get(self, category, default=None):
        p = _category_file(category)
        return p if p else default

    def __getitem__(self, category):
        p = _category_file(category)
        if not p:
            raise KeyError(category)
        return p

    def __contains__(self, category):
        return category in _CAT_FILENAMES

    def keys(self):
        return _CAT_FILENAMES.keys()

    def items(self):
        uid = _current_uid()
        return [(c, _category_file(c, uid)) for c in _CAT_FILENAMES]

    def values(self):
        uid = _current_uid()
        return [_category_file(c, uid) for c in _CAT_FILENAMES]


class _LiveCatFiles:
    """MEMORY_CAT_FILES replacement — (file, key) per current uid."""

    def get(self, category, default=None):
        try:
            return (MEMORY_FILE_MAP[category], MEMORY_KEY_NAMES.get(category, "items"))
        except KeyError:
            return default

    def __getitem__(self, category):
        return (MEMORY_FILE_MAP[category], MEMORY_KEY_NAMES.get(category, "items"))

    def __iter__(self):
        return iter(_CAT_FILENAMES.keys())

    def items(self):
        for c in _CAT_FILENAMES.keys():
            yield (c, (MEMORY_FILE_MAP[c], MEMORY_KEY_NAMES.get(c, "items")))

    def keys(self):
        return _CAT_FILENAMES.keys()

    def __len__(self):
        return len(_CAT_FILENAMES)

    def __contains__(self, category):
        return category in _CAT_FILENAMES


MEMORY_FILE_MAP = _LiveFileMap()
MEMORY_CAT_FILES = _LiveCatFiles()


# --------------------------------------------------------------------------- #
# dynamic attribute resolution (PEP 562)
# --------------------------------------------------------------------------- #
def _resolve(name: str):
    uid = _current_uid()
    if name == "RECENT_CONTEXT_CACHE":
        return _recent_cache.setdefault(uid, {})
    if name == "DATA_DIR":
        return _data_dir(uid)
    if name == "HISTORY_DIR":
        return _hist_dir(uid)
    if name in _LEGACY:
        if uid == "owner":
            return _LEGACY[name]
        base = _root(uid)
        if name == "SUMMARY_FILE":
            return os.path.join(base, "chat_summary.txt")
        fn = os.path.basename(_LEGACY[name])
        return os.path.join(_data_dir(uid), fn)
    raise AttributeError(f"module 'memory.paths' has no attribute {name!r}")


def __getattr__(name: str):
    if name in _DYNAMIC or name in ("RECENT_CONTEXT_CACHE", "DATA_DIR", "HISTORY_DIR"):
        return _resolve(name)
    raise AttributeError(f"module 'memory.paths' has no attribute {name!r}")


# Convenience helpers used by some callers / tests
# (set_uid / get_uid / safe_uid are imported from tenant_ctx at the top)

def ensure_user_dirs(uid=None):
    d = _root(uid)
    os.makedirs(_data_dir(uid), exist_ok=True)
    os.makedirs(_hist_dir(uid), exist_ok=True)
    return d
