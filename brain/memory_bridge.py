import json
import re
import time
import threading
from datetime import datetime
from memory import chat as _mchat
from memory.paths import MEMORY_FILE_MAP, CONTEXT_WINDOW


def _resolve_brain():
    """main.py ka MuskuBrain instance — optional (Musku Live save path)."""
    try:
        import main
        return getattr(main, "brain", None)
    except Exception:
        return None


def auto_extract_and_learn(brain, user_text):
    """Pro Feature: Background AI Memory Extractor (category-based)
    Conversation se important facts nikale aur sahi category file me store kare.
    - Dedup: repeated/pehle se stored fact dobara nahi save hota (sirf chat me).
    - Rate limit se bachne ke liye har 30 sec me ek baar hi call hota hai."""
    now = time.time()
    if now - getattr(brain, '_last_extract_at', 0) < 30.0:
        return
    brain._last_extract_at = now
    try:
        extraction_prompt = f"""Analyze the user statement. Agar wo koi important personal fact share kar raha hai,
to usse exactly ek JSON object me extract karo. Categories:
- "people": user ke jaante/dost/family/log ke baare me (naam, rishta, unki baatein, kya pasand)
- "places": jagah (ghar, work, school, gaya hua, pasandida jagah)
- "passion": kaam/profession/parhani/business/editing/trading/khwahishein/goals
- "preferences": pasand/napasand (khana, mausam, music, hobbies, topics)
- "pc_command": PC/computer control commands ka pattern (jaise app kholna, gaana, file)
- "profile": user ke baare general fact (habit, personality, family)
- "reminder": user ne koi kaam/time-pe yaad dilane ko kaha ho, with a "when" field (relative time in Hindi/English jaise "2 ghante me", "kal subah 9 baje", "5 minute baad") - ONLY jab user explicitly reminder/yaad-dilana kahe.
Agar koi important fact nahi hai (sirf greeting, sawaal, ya bekaar baat), to sirf "NONE" likho.
Format sirf JSON ya NONE:
{{"category": "people|places|passion|preferences|pc_command|profile|reminder", "fact": "chhota clean fact in Hindi/English", "when": "relative time phrase (sirf reminder ke liye)"}}
User Statement: "{user_text}"
Output:"""
        from brain_core import _gemini_chat
        content = _gemini_chat(
            [{"role": "user", "content": extraction_prompt}],
            max_tokens=120,
            temperature=0,
        )
        if not content or "NONE" in content.upper():
            return
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            return
        try:
            data = json.loads(m.group(0))
        except Exception:
            return
        category = str(data.get("category", "profile")).strip() or "profile"
        fact = re.sub(r"\s+", " ", str(data.get("fact", "") or "")).strip()
        if category == "reminder":
            when = str(data.get("when", "") or "").strip()
            if fact and when:
                if brain._set_reminder(fact, when):
                    print(f"[Reminder+] {fact} @ {when}")
            return
        if category not in MEMORY_FILE_MAP:
            category = "profile"
        if fact and len(fact) >= 4:
            brain._save_memory(category, fact, source=user_text)
    except Exception as e:
        print(f"[Memory Extraction Error]: {e}")

def _extract_realtime_memory(brain, user_text):
    """Background LLM memory extraction for real-time proactive recall."""
    try:
        extract_prompt = (
            "Neeche diye gaye user ke text me se agar koi important fact hai toh extract karo:\n"
            "1. 'relations': Dost, family, relatives ke naam aur unse rishta.\n"
            "2. 'passion': User ka business, profession, aur uske career goals.\n"
            "3. 'places': Jagah jahan user ko jana hai ya ghoomna hai.\n"
            "4. 'preferences': Pasand/Napasand.\n"
            "5. 'pc_command': PC control, app paths, ya automation steps.\n"
            "6. 'finance': Paise ka hisaab, bills, udhaar, subscriptions.\n"
            "7. 'ideas': Naye startup, software, ya creative ideas.\n"
            "8. 'health': Diet, workout goals, sleep schedule.\n"
            "9. 'inventory': Samaan kahan rakha hai (keys, passwords, files).\n"
            "10. 'learning': Nayi skills, padhai, tutorials jo user seekh raha hai.\n"
            "11. 'tasks': Aaj ke daily task. Agar naya task de toh '[PENDING] task_details' likho. Agar bole ho gaya toh '[COMPLETED] task_details' likho.\n"
            "Ek hi JSON array likho. Har item:\n"
            '{"category": "relations|places|passion|preferences|pc_command|finance|ideas|health|inventory|learning|tasks|profile", "fact": "chhota clean fact"}\n'
            'Koi fact nahi hai toh sirf [] likho:\n\n'
            f"User said: {user_text}"
        )
        from brain_core import _gemini_chat
        ext_content = _gemini_chat(
            [{"role": "user", "content": extract_prompt}],
            max_tokens=200,
            temperature=0,
        )
        m = re.search(r"\[.*\]", ext_content, re.S)
        if m:
            for item in json.loads(m.group(0)):
                cat = str(item.get("category", "profile")).strip()
                fact = re.sub(r"\s+", " ", str(item.get("fact", "") or "")).strip()
                if cat in MEMORY_FILE_MAP and fact and len(fact) >= 4:
                    brain._save_memory(cat, fact, source="realtime-chat")
    except Exception as e:
        print(f"[Realtime Memory Extract Error]: {e}")

def save_chat_log(brain, user_text, musku_reply, extra=None, consolidate=True):
    from brain.response import _grammar_fix
    if brain is None:
        brain = _resolve_brain()
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    entry = {
        "time": now.strftime("%H:%M:%S"),
        "user_said": user_text,
        "musku_replied": _grammar_fix(musku_reply, lang="devanagari"),
    }
    if isinstance(extra, dict):
        safe_extra = {
            "search_query": str(extra.get("search_query", ""))[:200],
            "search_result": [
                {
                    "title": str(it.get("title", ""))[:120] if isinstance(it, dict) else "",
                    "point": str(it.get("point", ""))[:160] if isinstance(it, dict) else "",
                }
                for it in (extra.get("search_result") or [])[:6]
                if isinstance(it, dict)
            ],
        }
        entry.update(safe_extra)
    _mchat.save_chat(date_str, entry)
    
    try:
        from memory import turn_context as _tctx
        _tctx.update_after_turn(user_text, entry["musku_replied"])
        _cele = _tctx.claim_streak_celebration()
        if _cele:
            try:
                from realtime.event_bus import bus
                bus.publish("RIDDLE_STREAK", _cele)
            except Exception:
                pass
    except Exception as e:
        print(f"[TurnContext Error]: {e}")

    try:
        from brain import conversation as _conv
        _conv.record_exchange(user_text, entry["musku_replied"])
    except Exception:
        pass
    
    # Rolling summary jab aaj ki file 10 se zyada ho
    threading.Thread(target=_maybe_rolling_summary, args=(date_str,), daemon=True).start()
    
    # PHASE 4: Deep multi-turn consolidation (ADD/UPDATE/REMOVE) + lightweight extract
    if consolidate and brain is not None:
        threading.Thread(target=_consolidate_background, args=(user_text,), daemon=True).start()


def _consolidate_background(user_text):
    """Deep recollection engine — multi-turn slice se ADD/UPDATE/REMOVE. Non-blocking.
    Saath me single-message lightweight extract bhi (fallback)."""
    try:
        ring = _mchat.load_recent_turns_ring()
        built = []
        for e in ring[-12:]:
            u = (e.get("user_said") or "").strip()
            r = (e.get("musku_replied") or "").strip()
            if u:
                built.append({"role": "user", "text": u})
            if r:
                built.append({"role": "model", "text": r})
        from memory.consolidate import process_conversation_slice
        process_conversation_slice(built[-14:])
    except Exception as e:
        print(f"[Consolidate Background Error]: {e}")
    brain = _resolve_brain()
    if brain is not None:
        _extract_realtime_memory(brain, user_text)


def _maybe_rolling_summary(date_str):
    """10+ entries par purani chat ka summary background me."""
    try:
        history = _mchat.load_chats_for_date(date_str)
        if len(history) <= CONTEXT_WINDOW:
            return
        brain = _resolve_brain()
        if brain is not None:
            brain._summarize_old_history(history)
    except Exception as e:
        print(f"[Summary Trigger Error]: {e}")
