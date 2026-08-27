# memory/store.py - Categorical memory + reminders storage (pure data layer).
# brain.py ke andar jo memory I/O tha, woh sab yahan hai. Functions pure hain —
# brain, path/global state se chhoti chhoti didn't depend; isliye brain ke
# wrappers bahut thin reh gaye. Har function fail-safe hai (kabhi crash nahi).
import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta

from . import paths


def mem_hash(fact):
    """Fact ka canonical dedup key — whitespace + chhota + sha256 hash."""
    norm = re.sub(r"\s+", " ", str(fact or "")).strip().lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16] if norm else ""


def new_mem_id():
    """Random short memory id (consolidation UPDATE/REMOVE ke liye)."""
    return os.urandom(4).hex()


def days_since(date_str):
    """'YYYY-MM-DD HH:MM' (ya sirf date) se aaj tak ke din."""
    try:
        s = str(date_str or "")
        fmt = "%Y-%m-%d %H:%M" if len(s) >= 16 else "%Y-%m-%d"
        return (datetime.now() - datetime.strptime(s[:16], fmt)).days
    except Exception:
        return 999


def load_profile():
    """Load user profile dictionary safely."""
    try:
        from personal_profile import load_profile as _lp
        return _lp() or {}
    except Exception:
        return {}

def load_file(file, key):
    """Category memory file ko load karta hai (fail-safe). List ya []."""
    try:
        if file and os.path.exists(file):
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data.get(key, []) or []
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _read_json(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback


def save_memory(category, fact, source="", importance=0.5):
    """Ek high-value fact ko sahi category file me aur Cloud Firestore me store karta hai.
    Returns True (nayi entry) / False (duplicate ya invalid)."""
    fact = re.sub(r"\s+", " ", str(fact or "")).strip()
    if not fact or len(fact) < 4:
        return False
    key = mem_hash(fact)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        os.makedirs(paths.DATA_DIR, exist_ok=True)
        with paths.LOCK:
            index = _read_json(paths.MEMORY_INDEX_FILE, {"facts": {}})
            index.setdefault("facts", {})
            if key in index["facts"]:
                bump_memory(category, fact, key)
                return False
            target = paths.MEMORY_FILE_MAP.get(category, paths.PROFILE_FILE)
            data = _read_json(target, {})
            keyname = paths.MEMORY_KEY_NAMES.get(category, "items")
            data.setdefault(keyname, [])
            data[keyname].append({
                "id": new_mem_id(),
                "fact": fact,
                "source": (source or "")[:60],
                "t": now,
                "importance": float(importance),
                "times_mentioned": 1,
                "last_seen": now,
            })
            data[keyname] = data[keyname][-paths.MEMORY_MAX_PER_CATEGORY:]
            with open(target, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            index["facts"][key] = {"category": category, "t": now}
            with open(paths.MEMORY_INDEX_FILE, "w", encoding="utf-8") as f:
                json.dump(index, f, indent=4, ensure_ascii=False)
            print(f"[Mem+] [{category}] {fact}")

            # Firestore persistence for authenticated user
            try:
                from tenant_ctx import get_uid
                from firebase.firestore import save_categorical_memory_fs
                uid = get_uid()
                if uid:
                    save_categorical_memory_fs(uid, category, data[keyname])
            except Exception as fe:
                pass

            return True
    except Exception as e:
        print(f"[Memory Write Error]: {e}")
        return False


def bump_memory(category, fact, key):
    """Duplicate mention pe entry ka times_mentioned++ + last_seen refresh.
    Chhota helper: pehle se LOCK hold hoke (dedup branch me) bulao."""
    try:
        target = paths.MEMORY_FILE_MAP.get(category, paths.PROFILE_FILE)
        keyname = paths.MEMORY_KEY_NAMES.get(category, "items")
        data = _read_json(target, {})
        for e in data.get(keyname, []):
            if mem_hash(e.get("fact", "")) == key:
                e["times_mentioned"] = int(e.get("times_mentioned", 1)) + 1
                e["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                break
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception:
        pass


def _locate_entry(mem_id=None, fact=None):
    """Kisi id ya fact se entry ka (file, keyname, index) locate karta hai.
    Returns (file_path, keyname, index) ya None."""
    for category, (file, keyname) in paths.MEMORY_CAT_FILES.items():
        try:
            data = _read_json(file, {})
            entries = data.get(keyname, [])
            for i, e in enumerate(entries):
                fact_txt = (e.get("fact") if isinstance(e, dict) else str(e)) or ""
                if mem_id and str(e.get("id") or "") == str(mem_id):
                    return file, keyname, i
                if (not mem_id and fact and mem_hash(fact_txt) == mem_hash(fact)):
                    return file, keyname, i
        except Exception:
            continue
    return None


def update_memory_entry(mem_id=None, fact=None, category=None, new_fact=None):
    """Existing memory entry ko UPDATE karta hai (text/category badalna).
    Returns True/False. Id na mile to same-category fact fallback."""
    loc = _locate_entry(mem_id=mem_id, fact=fact)
    if not loc:
        return False
    file, keyname, idx = loc
    try:
        with paths.LOCK:
            data = _read_json(file, {})
            entries = data.get(keyname, [])
            if idx >= len(entries):
                return False
            e = entries[idx]
            if isinstance(e, dict):
                if new_fact:
                    e["fact"] = re.sub(r"\s+", " ", str(new_fact)).strip()
                if category and category in paths.MEMORY_FILE_MAP:
                    e["category"] = category
                e["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                e["times_mentioned"] = int(e.get("times_mentioned", 1)) + 1
            data[keyname] = entries
            with open(file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception:
        return False


def remove_memory_entry(mem_id=None, fact=None):
    """Existing memory entry ko REMOVE karta hai. Returns True/False."""
    loc = _locate_entry(mem_id=mem_id, fact=fact)
    if not loc:
        return False
    file, keyname, idx = loc
    try:
        with paths.LOCK:
            data = _read_json(file, {})
            entries = data.get(keyname, [])
            if idx < len(entries):
                del entries[idx]
            data[keyname] = entries
            with open(file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception:
        return False


def apply_transactions(transactions):
    """Consolidation engine se aayi transactions apply karta hai.
    transactions = [{"action": "ADD|UPDATE|REMOVE", "id", "category", "text"}].
    Returns applied transactions list."""
    applied = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for trx in transactions or []:
        if not isinstance(trx, dict):
            continue
        action = str(trx.get("action") or "").strip().upper()
        mem_id = str(trx.get("id") or "").strip()
        category = str(trx.get("category") or "profile").strip()
        text = re.sub(r"\s+", " ", str(trx.get("text") or "")).strip()
        if category not in paths.MEMORY_FILE_MAP:
            category = "profile"
        try:
            if action == "REMOVE":
                if remove_memory_entry(mem_id=mem_id, fact=text):
                    applied.append(trx)
            elif action == "UPDATE":
                if update_memory_entry(mem_id=mem_id, fact=text, category=category, new_fact=text):
                    applied.append(trx)
            else:  # ADD
                if save_memory(category, text, source="consolidation"):
                    applied.append(trx)
        except Exception:
            continue
    return applied


def prune_memory(stale_days=14):
    """Purani + weak facts ko memory se demote karta hai.
    Condition: last_seen > stale_days purana AUR times_mentioned <= 1 AUR
    importance < 0.6. Strong/recent facts chhoot jaate hain. Returns count."""
    pruned = 0
    for category, (file, keyname) in paths.MEMORY_CAT_FILES.items():
        if category == "pc_command":
            continue  # PC commands alag cap/replay system me manage hote hain
        try:
            with paths.LOCK:
                data = _read_json(file, {})
                kept = []
                for e in data.get(keyname, []):
                    if (days_since(e.get("last_seen") or e.get("t")) > stale_days
                            and int(e.get("times_mentioned", 1)) <= 1
                            and float(e.get("importance", 0.5)) < 0.6):
                        pruned += 1
                        continue
                    kept.append(e)
                data[keyname] = kept
                with open(file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception:
            pass
    return pruned


def parse_relative_time(phrase):
    """'5 minute baad', '2 hour me', '1 ghante baad', 'kal subah' etc.
    -> ISO due_at string. Na samjhe to None."""

    def duration(n, unit):
        mult = {"second": 1, "sec": 1, "minute": 60, "min": 60, "hour": 3600,
                "ghanta": 3600, "ghante": 3600, "din": 86400, "day": 86400}.get(unit.lower())
        if not mult:
            return None
        return datetime.now() + timedelta(seconds=n * mult)

    p = re.sub(r"\s+", " ", str(phrase or "").lower()).strip()
    km = {"minute": ["minute", "min", "mina", "mi"], "hour": ["hour", "hourr", "ghante"],
          "second": ["second"], "day": ["day", "din"]}
    for unit, keys in km.items():
        m = re.search(r"(\d+)\s*(" + "|".join(keys) + r")", p)
        if m:
            return duration(int(m.group(1)), unit).strftime("%Y-%m-%d %H:%M")
    if "kal subah" in p or "tomorrow morning" in p:
        return (datetime.now() + timedelta(days=1)).replace(hour=9, minute=0).strftime("%Y-%m-%d %H:%M")
    if "kal" in p or "tomorrow" in p:
        return (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    m = re.search(r"(\d{1,2})[.:](\d{2})", p)  # absolute "15:30"
    if m:
        return (datetime.now().replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0)).strftime("%Y-%m-%d %H:%M")
    return None


def set_reminder(fact, when_phrase):
    """Relative time parse se due_at ko reminders.json me store karta hai."""
    due = parse_relative_time(when_phrase)
    if not due:
        return False
    try:
        os.makedirs(paths.DATA_DIR, exist_ok=True)
        with paths.LOCK:
            rem = _read_json(paths.REMINDERS_FILE, {"reminders": []})
            rem.setdefault("reminders", [])
            rem["reminders"].append({
                "id": int(time.time() * 1000),
                "fact": fact,
                "due_at": due,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "fired": False,
            })
            with open(paths.REMINDERS_FILE, "w", encoding="utf-8") as f:
                json.dump(rem, f, indent=4, ensure_ascii=False)
        return True
    except Exception:
        return False


def pop_due_reminders():
    """Due reminders ko fire-and-mark karta hai.
    Returns: fired fact strings ki list (speak/log brain karta hai)."""
    due_now = datetime.now().strftime("%Y-%m-%d %H:%M")
    fired = []
    try:
        with paths.LOCK:
            rem = _read_json(paths.REMINDERS_FILE, {"reminders": []})
            for r in rem.get("reminders", []):
                if not r.get("fired") and str(r.get("due_at", "")) <= due_now:
                    r["fired"] = True
                    fired.append(r.get("fact", ""))
            with open(paths.REMINDERS_FILE, "w", encoding="utf-8") as f:
                json.dump(rem, f, indent=4, ensure_ascii=False)
    except Exception:
        return []
    return fired


def load_all(max_per=8):
    """Saari categorical memories ko ek dict me merge (LLM context ke liye)."""
    return {
        "relations": load_file(paths.RELATIONS_FILE, "relations")[-max_per:],
        "places": load_file(paths.PLACES_FILE, "places")[-max_per:],
        "passion": load_file(paths.PASSION_FILE, "passion")[-max_per:],
        "preferences": load_file(paths.PREFERENCES_FILE, "preferences")[-max_per:],
        "pc_commands": load_file(paths.PC_MEMORY_FILE, "commands")[-max_per:],
        "finance": load_file(paths.FINANCE_FILE, "finance")[-max_per:],
        "ideas": load_file(paths.IDEAS_FILE, "ideas")[-max_per:],
        "health": load_file(paths.HEALTH_FILE, "health")[-max_per:],
        "inventory": load_file(paths.INVENTORY_FILE, "inventory")[-max_per:],
        "learning": load_file(paths.LEARNING_FILE, "learning")[-max_per:],
        "tasks": load_file(paths.TASKS_FILE, "tasks")[-max_per:],
    }


def category_keywords(category):
    """Category file ke 'keywords' list load karta hai (fail-safe → [])."""
    pair = paths.MEMORY_CAT_FILES.get(category)
    if not pair:
        return []
    return _read_json(pair[0], {}).get("keywords", []) or []


def match_categories(user_text):
    """User text me jo category keywords mile unka set (ordered)."""
    low = str(user_text or "").lower()
    matched = []
    for category in paths.MEMORY_CAT_FILES:
        for kw in category_keywords(category):
            if kw and kw in low:
                matched.append(category)
                break
    return matched


def load_routed(user_text):
    """Keyword-based memory load — matched categories poore (last 10), baaki
    halke (last 2). Always recent pc_commands (last 4)."""
    matched = match_categories(user_text)
    result = {}
    for category, (file, key) in paths.MEMORY_CAT_FILES.items():
        entries = load_file(file, key)
        if category in matched:
            result[category] = entries[-10:]
        else:
            result[category] = entries[-2:]
    result["pc_command"] = load_file(paths.PC_MEMORY_FILE, "commands")[-4:]
    return result


_LIVE_MEMORY_LABELS = {
    "profile": "Identity (Name, nick, profession, background)",
    "relations": "Key People & Relationships",
    "passion": "Work, Goals & Passion",
    "preferences": "Preferences & Tastes",
    "places": "Places",
    "emotional": "Emotional Highlights & Core Milestones",
    "goal": "Active Goals & Aspirations",
    "behavior": "Observed Traits & Behavioral Tendencies",
    "finance": "Finance",
    "ideas": "Ideas & Projects",
    "health": "Health",
    "learning": "Learning",
    "tasks": "Tasks & Reminders",
}

# MYRAA-style cognitive principles — model ko sikhate hain memories ko
# insaan ki tarah, naturally, casually baat me weave karna.
MEMORY_COGNITIVE_PRINCIPLES = (
    "CRITICAL MEMORY PRINCIPLES:\n"
    "- INTEGRATE MEMORIES INSTINCTIVELY: Yaadein conversation me bilkul smooth, natural aur human "
    "lagani chahiye. KABHI mat bolo 'meri memory ke hisaab se', 'maine record kar liya', "
    "'database me hai', 'aapne mujhe X date ko bataya tha'. Iske bajaye ek dost ki tarah casually "
    "baat me lao — jaise: 'Oh, since you're working on that website project...', "
    "'Aapka YouTube channel goal yad hai, kaisa chal raha hai?', 'Us startup wali baat ka kya hua?'.\n"
    "- COMPANIONSHIP DEPTH: Personality ko user ke goals, life events, emotional milestones aur "
    "preferences ke hisaab se adapt karo — empathy ke saath.\n"
    "- When asked 'yaad hai', 'last time kya kiya', 'hum kya kar rahe the' — seedha saved facts se "
    "jawab do. Guess mat karo; jo save hai wahi bolo."
)


def format_live_memory_card(max_per_cat=6):
    """Mayra-style persistent knowledge card for Gemini Live system prompt.
    Emotional/goal/behavior categories pehle (human-like), baaki utility."""
    lines = [
        "=== MUSKU PERSISTENT MEMORY (naturally yaad rakho — file/database mention mat karo) ===",
        MEMORY_COGNITIVE_PRINCIPLES,
    ]
    any_fact = False
    order = (
        "profile", "relations", "passion", "emotional", "goal", "behavior",
        "preferences", "places", "finance", "ideas", "health", "learning", "tasks",
    )
    for category in order:
        file_key = paths.MEMORY_FILE_MAP.get(category)
        keyname = paths.MEMORY_KEY_NAMES.get(category, "items")
        if not file_key:
            continue
        entries = load_file(file_key, keyname)[-max_per_cat:]
        facts = []
        for e in entries:
            f = (e.get("fact") if isinstance(e, dict) else str(e)).strip()
            if f and f not in facts:
                facts.append(f)
        if facts:
            any_fact = True
            label = _LIVE_MEMORY_LABELS.get(category, category)
            lines.append(f"* {label}:")
            lines.extend(f"  - {f}" for f in facts)
    if not any_fact:
        return ""
    lines.append("=" * 56)
    return "\n".join(lines)