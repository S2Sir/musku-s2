# memory/ - MUSKU ka memory/chat/reminder storage package (Phase-9 extraction).
#
# Dependency direction: memory <- brain. brain.py file-paths/JSON I/O khud NAHI
# karta — sab kuch yahan se aata hai. Brain ke methods thin wrappers ban gaye.
#
# Structure:
#   paths.py  -> single source of truth (paths, category maps, lock, caches)
#   store.py  -> categorical memory + reminders (pure data layer)
#   chat.py   -> per-date chat history + recent-context cache + date query
from . import chat, paths, store
from . import consolidate as mconsolidate
from .chat import (
    is_history_question,
    list_dates,
    load_chats_for_date,
    load_recent_context,
    resolve_date_query,
    save_chat,
)
from .store import (
    bump_memory,
    category_keywords,
    days_since,
    load_all,
    load_file,
    load_routed,
    match_categories,
    mem_hash,
    parse_relative_time,
    pop_due_reminders,
    prune_memory,
    save_memory,
    set_reminder,
    apply_transactions,
    update_memory_entry,
    remove_memory_entry,
)

__all__ = [
    "paths",
    "store",
    "chat",
    "mconsolidate",
    "mem_hash",
    "days_since",
    "load_file",
    "save_memory",
    "bump_memory",
    "prune_memory",
    "parse_relative_time",
    "set_reminder",
    "pop_due_reminders",
    "load_all",
    "category_keywords",
    "match_categories",
    "load_routed",
    "save_chat",
    "load_chats_for_date",
    "load_recent_context",
    "list_dates",
    "resolve_date_query",
    "is_history_question",
    "apply_transactions",
    "update_memory_entry",
    "remove_memory_entry",
]
