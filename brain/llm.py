import os
import time
import json
from collections import deque
from threading import Lock
from google import genai

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")

# Stable text models (docs-verified 2026-08): gemini-2.5-flash/-lite dead (shutdown
# chain). Primary = flash-lite (high RPM, full-day), backup = flash (emergency/429).
# brain_core.py ke GEMINI_MODEL/GEMINI_MODEL_BACKUP se aligned — ek hi source.
GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_MODEL_BACKUP = "gemini-3.5-flash"
GEMINI_MAX_PER_MIN = 14

_GEMINI_CALL_TIMES = deque()
_GEMINI_RATE_LOCK = Lock()
_LLM_GEMINI_CACHE = {}  # keyed by api_key (per-user multi-tenant)


def get_gemini_client(api_key=None):
    """Gemini client lazy load + cache. Per-user key supported (multi-tenant).

    If api_key is provided (a user's own key), build/cache a client for it.
    Otherwise fall back to environment variable or config.json key.
    """
    if api_key:
        cached = _LLM_GEMINI_CACHE.get(api_key)
        if cached:
            return cached
        try:
            client = genai.Client(api_key=api_key)
            _LLM_GEMINI_CACHE[api_key] = client
            return client
        except Exception:
            return None

    env_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    if env_key:
        cached = _LLM_GEMINI_CACHE.get(env_key)
        if cached:
            return cached
        try:
            client = genai.Client(api_key=env_key)
            _LLM_GEMINI_CACHE[env_key] = client
            return client
        except Exception:
            pass

    client = _LLM_GEMINI_CACHE.get("__global__")
    if client:
        return client
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            key = cfg.get("gemini_api_key") or cfg.get("google_api_key") or ""
            if key:
                client = genai.Client(api_key=key)
                _LLM_GEMINI_CACHE["__global__"] = client
                return client
    except Exception:
        pass
    return None
            _LLM_GEMINI_CACHE["__global__"] = client
            return client
    except Exception:
        pass
    return None

def acquire_gemini_slot():
    """Rate-limit gate: 1 minute me MAX se zyada Gemini calls na ho."""
    while True:
        now = time.time()
        with _GEMINI_RATE_LOCK:
            while _GEMINI_CALL_TIMES and now - _GEMINI_CALL_TIMES[0] >= 60.0:
                _GEMINI_CALL_TIMES.popleft()
            if len(_GEMINI_CALL_TIMES) < GEMINI_MAX_PER_MIN:
                _GEMINI_CALL_TIMES.append(now)
                return
            wait = 60.0 - (now - _GEMINI_CALL_TIMES[0])
        time.sleep(min(wait + 0.05, 1.0))

def gemini_chat(messages, max_tokens=200, temperature=0.7, model=None, api_key=None):
    """Unified Gemini helper - standardized chat interface.
    messages = [{'role': 'system'|'user', 'content': ...}]. Returns text ('' on fail).
    api_key: per-user Gemini key (multi-tenant); falls back to global key if None."""
    client = get_gemini_client(api_key)
    if not client:
        return ""
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    user = "\n\n".join(m["content"] for m in messages if m["role"] == "user")
    model_name = model or GEMINI_MODEL
    config = {
        "temperature": temperature,
        "max_output_tokens": max_tokens,
    }
    if "lite" not in model_name:
        config["thinking_config"] = {"thinking_budget": 0}
    if system:
        config["system_instruction"] = system
    acquire_gemini_slot()
    attempts = [model_name]
    if model is None:
        attempts.append(GEMINI_MODEL_BACKUP)
    
    for m in attempts:
        try:
            resp = client.models.generate_content(
                model=m, contents=user, config=config
            )
            text = (resp.text or "").strip()
            if text:
                return text
        except Exception as e:
            print(f"[Gemini Fallback Error {m}]: {e}")
            if m == attempts[-1]:
                pass
            else:
                time.sleep(1.0)
    return ""
