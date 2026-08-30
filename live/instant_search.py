"""instant_search.py — Live voice me turant Google search (Mayra-style).

Gemini tool call ka wait nahi — user ke bolte hi detect + search + results inject.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time

_lock = threading.Lock()
_last: dict = {"q": "", "at": 0.0, "summary": "", "voice_brief": "", "highlights": []}
_prefetch_lock = threading.Lock()
_wait_lock = threading.Lock()
_wait_sent_for = ""

_SEARCH_VERBS = re.compile(
    r"\b(search|dhundh|dhundo|dhoondh|dhoondho|khoj|google|find|result)\b",
    re.I,
)
_ABOUT_PHRASES = re.compile(
    r"\b(ke bare me|ke baare me|ke baare|about|ka price|ki price|kya hai|"
    r"kya hua|kitna hai|kitne ka|news|update)\b",
    re.I,
)
_FOLLOW_UP = re.compile(
    r"\b(result|results|rijalt|aaya|aaye|mil[aey]|kya mila|kaun hai|kaun h|"
    r"batao|samjhao|explain|bataye|search hua|search hui|kya aaya)\b",
    re.I,
)
_WIKI_JUNK = re.compile(
    r"(Read more|\.\.\.|·\s*Bel|\(\d{4}-\d{2}-\d{2}\)|\(\u0906\u092f\u0941\s*\d+\)|"
    r"Facebook ·|reactions ·|\d+\+ reactions)",
    re.I,
)


def get_profile_language() -> str:
    try:
        from language_policy import normalize_language

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg_path = os.path.join(root, "config.json")
        with open(cfg_path, encoding="utf-8") as f:
            lang = json.load(f).get("language", "hinglish")
        return normalize_language(lang)
    except Exception:
        return "hinglish"


def prepare_voice_text(text: str, lang: str | None = None) -> str:
    """Search snippet ko profile language ke liye tayyar karo."""
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return cleaned
    cleaned = _WIKI_JUNK.sub("", cleaned).strip(" ·-|")
    lang = lang or get_profile_language()
    if lang == "hindi":
        return cleaned
    if lang == "english":
        return cleaned
    try:
        from brain_core import deva_to_hinglish

        if re.search(r"[\u0900-\u097F]", cleaned):
            cleaned = deva_to_hinglish(cleaned)
    except Exception:
        pass
    return cleaned


def is_search_command(text: str) -> bool:
    """Browser/Google explicit search — hook + prefetch ke liye."""
    try:
        from live.search_policy import is_explicit_browser_search
        return is_explicit_browser_search(text)
    except Exception:
        return False


def extract_query(text: str) -> str:
    from control import _extract_web_search_query
    return (_extract_web_search_query(text) or "").strip()


def get_cached_search_hit(max_age: float = 180.0) -> dict | None:
    with _lock:
        q = _last.get("q") or ""
        at = float(_last.get("at") or 0)
        if not q or time.time() - at > max_age:
            return None
        return {
            "query": q,
            "summary": _last.get("summary") or "",
            "voice_brief": _last.get("voice_brief") or "",
            "highlights": list(_last.get("highlights") or []),
            "text": "",
            "ok": bool(_last.get("highlights") or _last.get("voice_brief")),
            "cached": True,
        }


def is_search_follow_up(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) < 4 or is_search_command(t):
        return False
    if not _FOLLOW_UP.search(t.lower()):
        return False
    hit = get_cached_search_hit()
    if not hit:
        return False
    q = (hit.get("query") or "").lower()
    if q:
        for word in q.split()[:3]:
            if len(word) >= 3 and word in t.lower():
                return True
    return True


def resolve_search_explain(text: str) -> dict | None:
    """Naya search ya pichhle search ka follow-up explain."""
    if is_search_follow_up(text):
        return get_cached_search_hit()
    if is_search_command(text):
        return maybe_run_instant_search(text)
    return None


def parse_search_voice_brief(summary: str, highlights: list | None = None) -> str:
    """Google search output se awaaz ke liye clean facts."""
    lang = get_profile_language()
    if highlights:
        lines = []
        for h in highlights[:4]:
            line = re.sub(r"^\d+\)\s*", "", str(h).strip())
            if " — " in line:
                title, snip = line.split(" — ", 1)
                title = prepare_voice_text(title.strip(), lang)
                snip = prepare_voice_text(snip.strip()[:140], lang)
                lines.append(f"{title}: {snip}")
            elif line:
                lines.append(prepare_voice_text(line[:180], lang))
        if lines:
            return "\n".join(f"- {ln}" for ln in lines)

    text = str(summary or "")
    if "Top results:" in text:
        chunk = text.split("Top results:", 1)[1]
        chunk = chunk.split(". Ab awaaz", 1)[0].split(". Musku", 1)[0]
        parts = [p.strip() for p in chunk.split("|") if p.strip()]
        lines = []
        for p in parts[:4]:
            p = re.sub(r"^\d+\)\s*", "", p)
            if p:
                lines.append(prepare_voice_text(p[:200], lang))
        if lines:
            return "\n".join(f"- {ln}" for ln in lines)

    cleaned = re.sub(
        r"(Boss,|Haan,)\s*maine Google pe '[^']+' search kar diya\.?\s*",
        "",
        text,
        flags=re.I,
    )
    cleaned = re.sub(r"Ab awaaz se.*", "", cleaned, flags=re.I).strip()
    cleaned = prepare_voice_text(cleaned, lang)
    return cleaned[:900] if cleaned else prepare_voice_text(text[:400], lang)


def _pack_from_google_search(q: str, text: str, summary: str) -> dict:
    highlights = []
    if "Top results:" in summary:
        chunk = summary.split("Top results:", 1)[1]
        chunk = chunk.split(". Ab awaaz", 1)[0]
        highlights = [h.strip() for h in chunk.split("|") if h.strip()]
    voice_brief = parse_search_voice_brief(summary, highlights)
    ok = bool(highlights) or "khul gayi" in summary.lower() or len(voice_brief) > 40
    return {
        "query": q,
        "summary": summary,
        "voice_brief": voice_brief,
        "highlights": highlights,
        "text": text,
        "ok": ok,
        "cached": False,
    }


def open_visible_search(query_or_text: str) -> bool:
    """Musku 2.0 does not control desktop browsers directly."""
    return False


def prefetch_instant_search(text: str) -> None:
    """Background me full search — USER_SPEECH_FINAL se pehle results ready."""
    if not is_search_command(text):
        return

    def _work():
        with _prefetch_lock:
            maybe_run_instant_search(text)

    threading.Thread(target=_work, daemon=True, name="SearchPrefetch").start()


def reset_search_wait_turn() -> None:
    global _wait_sent_for
    with _wait_lock:
        _wait_sent_for = ""


def build_search_wait_prompt(query: str) -> str:
    q = (query or "ye topic").strip()
    lang = get_profile_language()
    if lang == "english":
        line = f"Okay boss, I'm searching Google for {q} — one second."
    elif lang == "hindi":
        line = f"ठीक है बॉस, मैं {q} के बारे में Google पर खोज कर रही हूँ — एक सेकंड।"
    else:
        line = (
            f"Theek hai boss, main {q} ke baare me Google pe search kar rahi hoon — ek second."
        )
    return (
        "[INTERNAL — SEARCH chal rahi hai. Musku, abhi SIRF neeche ki EK line bolo. "
        "Uske alawa KUCH mat bolo — sorry, fail, gadbad, dobara try BILKUL nahi. "
        "Tool mat call karo. Results alag message me aayenge.]\n"
        + line
    )


def send_search_wait_once(text: str) -> None:
    """Partial transcript pe ek baar hold-prompt — sorry se pehle."""
    global _wait_sent_for
    if not is_search_command(text):
        return
    q = extract_query(text) or text[:48].strip()
    key = q.lower()
    with _wait_lock:
        if _wait_sent_for == key:
            return
        _wait_sent_for = key
        prompt = build_search_wait_prompt(q)
    try:
        from live.browser_live_ws import browser_live_ws
        from tenant_ctx import get_uid

        browser_live_ws.send_proactive_prompt_direct(prompt, uid=get_uid())
    except Exception:
        pass


def maybe_run_instant_search(text: str) -> dict | None:
    """Detect + run google_search. Same query 8s me dubara nahi."""
    if not is_search_command(text):
        return None
    q = extract_query(text)
    if not q or len(q) < 2:
        return None

    now = time.time()
    with _lock:
        if _last.get("q") == q.lower() and now - float(_last.get("at") or 0) < 8.0:
            hit = {
                "query": q,
                "summary": _last.get("summary") or "",
                "voice_brief": _last.get("voice_brief") or "",
                "highlights": list(_last.get("highlights") or []),
                "text": text,
                "ok": bool(_last.get("highlights") or _last.get("voice_brief")),
                "cached": True,
            }
            return hit

    try:
        from brain.search import web_search
        summary = web_search(q) or ""
    except Exception as exc:
        summary = f"Search error: {exc}"

    hit = _pack_from_google_search(q, text, summary)
    with _lock:
        _last.update({
            "q": q.lower(),
            "at": now,
            "summary": summary,
            "voice_brief": hit.get("voice_brief") or "",
            "highlights": hit.get("highlights") or [],
        })

    try:
        print(
            f"[InstantSearch] '{q}' ok={hit.get('ok')} brief={len(hit.get('voice_brief') or '')}"
        )
    except Exception:
        pass
    return hit


def format_spoken_search_reply(query: str, voice_brief: str) -> str:
    """Mayra-style — poora jawab jo Musku seedha bol sakti hai."""
    lang = get_profile_language()
    facts = []
    for line in (voice_brief or "").split("\n"):
        line = line.strip().lstrip("- ").strip()
        if not line:
            continue
        if ": " in line:
            title, body = line.split(": ", 1)
            title = prepare_voice_text(title.strip(), lang)
            body = prepare_voice_text(body.strip()[:200], lang)
            if body:
                facts.append(body)
            elif title:
                facts.append(title[:200])
        else:
            facts.append(prepare_voice_text(line[:200], lang))

    q = prepare_voice_text((query or "ye topic").strip(), lang)
    if not facts:
        if lang == "english":
            return (
                f"I searched Google for {q}. "
                "The browser has the results open for you."
            )
        if lang == "hindi":
            return (
                f"मैंने Google पर {q} खोज लिया है। "
                "ब्राउज़र में नतीजे खुल गए हैं।"
            )
        return (
            f"Maine Google pe {q} search kar liya hai. "
            "Browser me results khul gaye hain, aap dekh sakte hain."
        )

    if lang == "english":
        intro = f"Yes, I searched Google for {q}."
        main = facts[0].rstrip(".")
        if len(facts) >= 2:
            extra = facts[1].rstrip(".")
            return f"{intro} Here's what I found — {main}. Also — {extra}."
        return f"{intro} Here's what I found — {main}."

    if lang == "hindi":
        intro = f"हाँ, मैंने {q} के बारे में Google पर खोज की।"
        main = facts[0].rstrip("।.")
        if len(facts) >= 2:
            extra = facts[1].rstrip("।.")
            return f"{intro} मुझे यह मिला — {main}। और एक और बात — {extra}।"
        return f"{intro} मुझे यह मिला — {main}।"

    intro = f"Haan, maine {q} ke baare me Google pe search kar liya."
    main = facts[0].rstrip(".")
    if len(facts) >= 2:
        extra = facts[1].rstrip(".")
        return (
            f"{intro} Mujhe ye mila — {main}. "
            f"Aur ek aur cheez — {extra}."
        )
    return f"{intro} Mujhe ye mila — {main}."


def build_spoken_prompt(spoken: str) -> str:
    """Gemini ko exact lines bolne ke liye — sorry/fail block + language lock."""
    lang = get_profile_language()
    if lang == "english":
        lang_rule = "Speak in pure English. "
    elif lang == "hindi":
        lang_rule = "Devanagari Hindi me bolo. "
    else:
        lang_rule = (
            "Roman Hinglish me bolo — poora jawab Hinglish me. "
            "English ya Devanagari sentences mat padho; simple Hinglish me samjhao. "
        )
    return (
        "[INTERNAL — Google search SUCCESS. Sorry, fail, gadbad, dobara try — "
        "ye sab BILKUL mat bolo. Tool mat call karo. Koi sawal mat puchho. "
        "'Kya jaanna chahte hain' / 'khaas jaanna chahte hain' mat puchho.]\n"
        f"Musku, ab turant awaaz se neeche diye results ko 2-4 natural sentences me samjhao — "
        f"{lang_rule}feminine, hamesha aap + Boss. Important points batao:\n"
        f"{spoken}"
    )


def build_inject_prompt(hit: dict) -> str:
    spoken = format_spoken_search_reply(
        hit.get("query") or "",
        hit.get("voice_brief") or hit.get("summary") or "",
    )
    return build_spoken_prompt(spoken)


def inject_search_explain(text: str) -> bool:
    """Search ya follow-up resolve karke Live session me inject karo."""
    hit = resolve_search_explain(text)
    if not hit or not hit.get("ok"):
        return False
    prompt = build_inject_prompt(hit)
    try:
        from live.browser_live_ws import browser_live_ws
        from tenant_ctx import get_uid

        browser_live_ws.send_proactive_prompt_direct(prompt, uid=get_uid())
        return True
    except Exception:
        pass
    return False
