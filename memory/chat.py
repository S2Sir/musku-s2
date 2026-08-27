# memory/chat.py - Chat history (per-date JSON files) + recent-context cache.
# musku_chat/<date>.json me har din ki baatein. brain.py ke history methods
# isi layer pe bast hain — bas entry-building brain ke paas rehta hai.
import json
import os
import re
from datetime import datetime, timedelta

from . import paths


def save_chat(date_str, entry):
    """Entry ko Cloud Firestore me save karta hai (Primary Source of Truth) + local JSON fallback."""
    user_said = entry.get("user_said") or entry.get("user") or ""
    musku_replied = entry.get("musku_replied") or entry.get("musku") or ""

    # Primary: Cloud Firestore persistence for authenticated UID
    try:
        from tenant_ctx import get_uid
        from firebase.firestore import save_chat_turn_fs
        uid = get_uid()
        if uid and user_said:
            save_chat_turn_fs(uid, date_str, user_said, musku_replied, meta={"time": entry.get("time", "")})
    except Exception as fe:
        print(f"[Firestore Chat Save Error]: {fe}")

    # Fallback: local JSON file
    try:
        os.makedirs(paths.HISTORY_DIR, exist_ok=True)
        file_path = os.path.join(paths.HISTORY_DIR, f"{date_str}.json")
        with paths.LOCK:
            history = []
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
            history.append(entry)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=4, ensure_ascii=False)
            _update_recent_turns_locked(entry, date_str)
    except Exception as e:
        print(f"[History Save Error]: {e}")
    finally:
        paths.RECENT_CONTEXT_CACHE.pop(datetime.now().strftime("%Y-%m-%d"), None)


def _update_recent_turns_locked(entry, date_str):
    """Last CONTEXT_WINDOW turns — restart ke baad bhi yaad (musku_data/recent_turns.json)."""
    try:
        os.makedirs(paths.DATA_DIR, exist_ok=True)
        ring = []
        if os.path.exists(paths.RECENT_TURNS_FILE):
            with open(paths.RECENT_TURNS_FILE, "r", encoding="utf-8") as f:
                ring = json.load(f)
        item = dict(entry)
        item["date"] = date_str
        ring.append(item)
        ring = ring[-paths.CONTEXT_WINDOW:]
        with open(paths.RECENT_TURNS_FILE, "w", encoding="utf-8") as f:
            json.dump(ring, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Recent Turns Save Error]: {e}")


def load_recent_turns_ring():
    """Persisted last N chat turns (cross-session). Missing file -> daily files se rebuild."""
    try:
        if os.path.exists(paths.RECENT_TURNS_FILE):
            with open(paths.RECENT_TURNS_FILE, "r", encoding="utf-8") as f:
                ring = json.load(f)
            if ring:
                return ring[-paths.CONTEXT_WINDOW:]
    except Exception:
        pass
    return load_last_n_entries()


def load_last_n_entries(n=None):
    """Daily history files se globally last N user+Musku pairs."""
    n = n or paths.CONTEXT_WINDOW
    try:
        dates = list_dates(limit=60)
        if not dates:
            return []
        collected = []
        for date_str in reversed(dates):
            for e in reversed(load_chats_for_date(date_str)):
                item = dict(e)
                item.setdefault("date", date_str)
                collected.append(item)
                if len(collected) >= n:
                    collected.reverse()
                    return collected
        collected.reverse()
        return collected
    except Exception:
        return []


def format_turns_for_prompt(entries):
    if not entries:
        return ""
    lines = []
    for e in entries:
        d = e.get("date", "")
        t = e.get("time", "")
        stamp = f"[{d} {t}] " if d else ""
        lines.append(f"{stamp}User: {e.get('user_said', '')}")
        lines.append(f"Musku: {e.get('musku_replied', '')}")
    return "\n".join(lines)


def load_recent_memory_context(n=None):
    """Prompt ke liye last N turns (persisted ring, fallback daily files)."""
    entries = load_recent_turns_ring()
    if n:
        entries = entries[-n:]
    return format_turns_for_prompt(entries)


def load_chat_summary(max_chars=800):
    try:
        if not os.path.exists(paths.SUMMARY_FILE):
            return ""
        with open(paths.SUMMARY_FILE, "r", encoding="utf-8") as f:
            text = f.read().strip()
        return text[:max_chars] if text else ""
    except Exception:
        return ""


def load_chats_for_date(date_str):
    """Kisi specific date ki chat history file load karta hai (list)."""
    try:
        file_path = os.path.join(paths.HISTORY_DIR, f"{date_str}.json")
        if not os.path.exists(file_path):
            return []
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def load_recent_context(today):
    """Aaj ki recent chat history se last CONTEXT_WINDOW messages (cached)."""
    if today in paths.RECENT_CONTEXT_CACHE:
        return paths.RECENT_CONTEXT_CACHE[today]
    try:
        file_path = os.path.join(paths.HISTORY_DIR, f"{today}.json")
        if not os.path.exists(file_path):
            paths.RECENT_CONTEXT_CACHE[today] = ""
            return ""
        with open(file_path, "r", encoding="utf-8") as f:
            chats = json.load(f)
        recent = chats[-paths.CONTEXT_WINDOW:] if len(chats) > paths.CONTEXT_WINDOW else chats
        if not recent:
            paths.RECENT_CONTEXT_CACHE[today] = ""
            return ""
        lines = []
        for e in recent:
            lines.append(f"User: {e.get('user_said', '')}")
            lines.append(f"Musku: {e.get('musku_replied', '')}")
        context = "\n".join(lines)
        paths.RECENT_CONTEXT_CACHE[today] = context
        return context
    except Exception:
        return ""


def list_dates(limit=14):
    """musku_chat me kaunsi dates ki files hain -> sorted list (recent)."""
    try:
        files = sorted(f for f in os.listdir(paths.HISTORY_DIR) if f.endswith(".json"))
        dates = [f.replace(".json", "") for f in files]
        return dates[-limit:]
    except Exception:
        return []


def is_history_question(user_text):
    """User purani date / kaam ke baare me poochh raha hai ya nahi."""
    text = (user_text or "").lower()
    q_markers = [
        "kya kiya", "kya kiya tha", "kya hua", "kya hua tha", "kya chala",
        "kya kaam", "kaam kiya", "us din", "us date", "kis din", "kis date",
        "history", "itihaas", "yaad", "bata do kya", "purana", "purani",
        "pichhle", "pichhla", "aaj se pehle", "tab kya", "wo din",
        "kya baat hui", "kya kaha", "kya bola",
        "last time", "last kaam", "last me", "last conversation",
        "abhi kya", "kya kar rahe", "kya kar rhe", "kya kar raha", "kya kar rahi",
        "pehle kya", "recent", "continue karo", "wahi kaam", "last wala",
        "hum kya kar", "humne kya", "maine kya", "aapne kya",
    ]
    return any(m in text for m in q_markers)


def resolve_date_query(user_text):
    """User ke message me se date samajhta hai -> 'YYYY-MM-DD' (ya None)."""
    text = (user_text or "").lower().strip()
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")

    # 1. Relative words: aaj / kal / parso
    if re.search(r"\b(parso|parson|tarsom)\b", text):
        return (today - timedelta(days=2)).strftime("%Y-%m-%d")
    if re.search(r"\b(kal|kall)\b", text) and "aaj kal" not in text and "kal se" not in text:
        return (today - timedelta(days=1)).strftime("%Y-%m-%d")
    if re.search(r"\baaj\b", text):
        return today_str

    # 2. Weekday names -> pichhla same weekday
    weekday_map = {
        "sunday": 0, "ravivar": 0, "itvar": 0, "itwaar": 0,
        "monday": 1, "somvar": 1, "somwaar": 1,
        "tuesday": 2, "mangalvar": 2, "mangalwaar": 2,
        "wednesday": 3, "budhvar": 3, "budhwaar": 3,
        "thursday": 4, "guruvar": 4, "guruwaar": 4, "virvar": 4,
        "friday": 5, "shukravar": 5, "shukrawaar": 5, "shukrawar": 5,
        "saturday": 6, "shaniwar": 6, "shaniwaar": 6,
    }
    for word, wday in weekday_map.items():
        if re.search(r"\b" + word + r"\b", text):
            days_back = (today.weekday() - wday) % 7
            if days_back == 0:
                days_back = 7
            return (today - timedelta(days=days_back)).strftime("%Y-%m-%d")

    # 3. Explicit date formats: 2026-08-05, 05/08/2026, 5-8-2026, 5 august
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", text)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"

    # 4. "5 august" / "5 aug 2026" / "august 5"
    month_map = {
        "january": 1, "jan": 1, "janavari": 1, "janwari": 1,
        "february": 2, "feb": 2, "farvari": 2,
        "march": 3, "mar": 3,
        "april": 4, "apr": 4,
        "may": 5,
        "june": 6, "jun": 6,
        "july": 7, "jul": 7,
        "august": 8, "aug": 8, "agast": 8,
        "september": 9, "sep": 9, "sitambar": 9,
        "october": 10, "oct": 10,
        "november": 11, "nov": 11,
        "december": 12, "dec": 12, "diceumber": 12,
    }
    for month_name, month_num in month_map.items():
        m = re.search(r"(\d{1,2})\s*(?:st|nd|rd|th)?\s+(" + month_name + r")\s*(\d{4})?", text)
        if m:
            day = int(m.group(1))
            year = int(m.group(3)) if m.group(3) else today.year
            return f"{year}-{month_num:02d}-{day:02d}"
        m = re.search(r"(" + month_name + r")\s+(\d{1,2})", text)
        if m:
            day = int(m.group(2))
            return f"{today.year}-{month_num:02d}-{day:02d}"
    return None