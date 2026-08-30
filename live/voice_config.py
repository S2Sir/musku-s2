"""voice_config.py - Gemini Live voice/model configuration (single source).

SIRF yahan voice moderate karna hai (model, voice, persona). Baaki live/
modules is config se values lete hain. Isme koi audio capture / playback /
Gemini logic nahi hai — sirf configuration.
"""
import json
import os

def _env_bool(name, default="0"):
    """Env flag helper."""
    if name in os.environ:
        return bool(int(os.environ[name]))
    return bool(int(default))
from personal_profile import BOSS_PERSONA_INSTRUCTION, TTS_STYLE_INSTRUCTION
try:
    from persona.abuse_policy import POLITE_BOUNDARY_BLOCK
except Exception:
    POLITE_BOUNDARY_BLOCK = ""

# --------------------------------------------------------------------------
# Gemini Live model (bina invent kiye — SDK/API supported name)
# Env se override ho sakta hai:  GEMINI_LIVE_MODEL
# Note: `gemini-3.1-flash-live-preview` Live ke liye verified default.
# --------------------------------------------------------------------------
DEFAULT_MODEL = os.environ.get(
    "GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview"
)

# Audio capture format (Mic -> Gemini)
INPUT_SAMPLE_RATE = 16000          # Hz
INPUT_CHANNELS = 1                 # mono
INPUT_SAMPLE_WIDTH = 2             # 16-bit
INPUT_FORMAT_MIME = "audio/pcm;rate=16000"

# Output audio rate (Gemini Live returns pcm L16) — blob mimeType se override
OUTPUT_SAMPLE_RATE = 24000         # Live default audio rate

# --------------------------------------------------------------------------
# Browser mic — WebView getUserMedia + echoCancellation.
# --------------------------------------------------------------------------
BROWSER_MIC_ENABLED = True

# Browser mic echo cancellation — ON by default for built-in mics.
# For headphones (no echo needed), set MUSKU_MIC_ECHO_CANCEL=0
# This prevents issues with headphone mics that don't support echo cancellation
MIC_ECHO_CANCELLATION = bool(int(os.environ.get("MUSKU_MIC_ECHO_CANCEL", "1")))

# Browser mic noise gate — OFF by default (continuous stream, Gemini VAD decides).
# Fan/noise false-trigger par env se ON karo: MUSKU_MIC_NOISE_GATE=1
MIC_NOISE_GATE_ENABLED = False
MIC_NOISE_FLOOR = float(os.environ.get("MUSKU_MIC_NOISE_FLOOR", "0.008"))
MIC_SPEECH_RMS = float(os.environ.get("MUSKU_MIC_SPEECH_RMS", "0.012"))
MIC_SPEECH_HANGOVER = int(os.environ.get("MUSKU_MIC_HANGOVER", "12"))

# Browser mic input gain — JS side ab adaptive boost karta hai (JS_MIC_GAIN).
# Isliye yahan default 1.0 (double-boost/clip se bachne ke liye). Override: MUSKU_MIC_GAIN
MIC_INPUT_GAIN = float(os.environ.get("MUSKU_MIC_GAIN", "1.0"))
MIC_METER_GAIN = float(os.environ.get("MUSKU_MIC_METER_GAIN", "2.8"))
# Browser (JS) side mic base boost — weak/headset mics jo ~1% level dete hain.
# JS adaptive gain iske upar auto-adjust karta hai. Override: MUSKU_JS_MIC_GAIN
JS_MIC_GAIN = float(os.environ.get("MUSKU_JS_MIC_GAIN", "3.0"))

# Browser Gemini VAD — default (no custom VAD) works best; optional override
BROWSER_VAD_SILENCE_MS = int(os.environ.get("MUSKU_BROWSER_VAD_SILENCE_MS", "350"))
BROWSER_VAD_USE_DEFAULT = bool(int(os.environ.get("MUSKU_BROWSER_VAD_DEFAULT", "1")))

# --------------------------------------------------------------------------
# INSTANT VOICE — latency-first defaults (MYRAA-style direct path)
# Override: MUSKU_INSTANT_VOICE=0 (to use larger buffers for stability)
# --------------------------------------------------------------------------
INSTANT_VOICE_MODE = bool(int(os.environ.get("MUSKU_INSTANT_VOICE", "1")))  # Default ON

# Mic chunk: 40ms for balanced latency and overhead @16kHz mono int16
CHUNK_DURATION_MS = 40
FRAME_BYTES = int(
    INPUT_SAMPLE_RATE * INPUT_SAMPLE_WIDTH * INPUT_CHANNELS * (CHUNK_DURATION_MS / 1000.0)
)

# Speaker output queue: chhota = kam latency
OUTPUT_QUEUE_MAX = int(os.environ.get(
    "MUSKU_OUTPUT_QUEUE", "24" if INSTANT_VOICE_MODE else "48"
))
OUTPUT_FRAMES_PER_BUFFER = int(os.environ.get(
    "MUSKU_OUTPUT_FRAMES", "128" if INSTANT_VOICE_MODE else "256"
))

# Send loop mic queue — chhota = user voice Gemini tak jaldi
SEND_QUEUE_MAX = int(os.environ.get(
    "MUSKU_SEND_QUEUE", "24" if INSTANT_VOICE_MODE else "80"
))

# Speaker drained + no AI audio → LISTENING (seconds)
SPEAKER_DRAIN_IDLE = float(os.environ.get(
    "MUSKU_SPEAKER_DRAIN_IDLE", "0.08" if INSTANT_VOICE_MODE else "0.25"
))

# TURN_COMPLETE background flush cap (instant mode me state block nahi karta)
TURN_FLUSH_TIMEOUT = float(os.environ.get(
    "MUSKU_FLUSH_TIMEOUT", "0.08" if INSTANT_VOICE_MODE else "2.0"
))

# TURN_COMPLETE: turant LISTENING (mic already open) — flush background me
INSTANT_LISTEN_RESTORE = bool(int(os.environ.get(
    "MUSKU_INSTANT_LISTEN", "1" if (INSTANT_VOICE_MODE and BROWSER_MIC_ENABLED) else "0"
)))

BROWSER_AUDIO_PLAYBACK = True

# Browser <-> /live WebSocket (no pywebview mic/audio bridge).
BROWSER_LIVE_WS = True
BROWSER_LIVE_WS_HOST = os.environ.get("MUSKU_LIVE_WS_HOST", "0.0.0.0")
# PaaS (RunxBuild/HF/Render) only exposes $PORT — if MUSKU_LIVE_WS_PORT not set, share HTTP PORT so single public port serves both / and /live
BROWSER_LIVE_WS_PORT = int(os.environ.get("MUSKU_LIVE_WS_PORT", os.environ.get("PORT", "8770")))

# Musku inline Live — thin /live bridge, Gemini session per browser WS client
MUSKU_INLINE_LIVE = _env_bool(
    "MUSKU_INLINE_LIVE", "1" if BROWSER_LIVE_WS else "0"
)

# Musku Live terminal debug logs — default OFF (MUSKU_LIVE_DEBUG=1)
MUSKU_LIVE_DEBUG = _env_bool("MUSKU_LIVE_DEBUG", "0")

# --------------------------------------------------------------------------
# Echo gate — PyAudio mic me browser jaisa AEC nahi hai.
# Browser mic ke saath bhi ON: SPEAKING me mic-to-Gemini block hota hai,
# taaki mouse-click/keyboard sound server-side barge-in (false interrupted)
# na trigger kare. Real user speech local barge-in se detect hoti hai
# (MIC_CHUNK_RAW_UNGATED feed) — isliye user interrupt ability intact.
# --------------------------------------------------------------------------
_ECHO_GATE_DEFAULT = "1"
ECHO_GATE_WHILE_SPEAKING = bool(int(os.environ.get("MUSKU_ECHO_GATE", _ECHO_GATE_DEFAULT)))

LOCAL_BARGE_IN_ENABLED = bool(int(os.environ.get(
    "MUSKU_LOCAL_BARGE_IN", "1" if ECHO_GATE_WHILE_SPEAKING else "0"
)))

VOICE_ROUTER_ENABLED = bool(int(os.environ.get("MUSKU_VOICE_ROUTER", "0")))

# Parallel search inject (off) — Gemini searchGoogle tool handles search + voice reply.
INSTANT_SEARCH_HOOK = bool(int(os.environ.get("MUSKU_INSTANT_SEARCH_HOOK", "0")))

LIVE_TOOLS_ENABLED = _env_bool("MUSKU_LIVE_TOOLS", "1")
LIVE_TOOLS_SLIM = _env_bool(
    "MUSKU_LIVE_TOOLS_SLIM",
    "1" if INSTANT_VOICE_MODE else "0",
)

SCREEN_SHARE_ENABLED = bool(int(os.environ.get(
    "MUSKU_SCREEN_SHARE", "0" if INSTANT_VOICE_MODE else "1"
)))
SCREEN_SHARE_ON_CONNECT = bool(int(os.environ.get("MUSKU_SCREEN_ON_CONNECT", "0")))
SCREEN_SHARE_INTERVAL = float(os.environ.get("MUSKU_SCREEN_INTERVAL", "1.0"))
SCREEN_SHARE_MAX_DIM = int(os.environ.get("MUSKU_SCREEN_MAX_DIM", "1280"))
SCREEN_SHARE_JPEG_QUALITY = int(os.environ.get("MUSKU_SCREEN_QUALITY", "60"))

# Local barge-in RMS threshold (0–1) while echo gate blocks Gemini mic feed
BARGE_IN_RMS_THRESHOLD = float(os.environ.get("MUSKU_BARGE_RMS", "0.12"))

# Gate-stuck: only THINKING/SPEAKING ultimate fallback (seconds)
VOICE_STUCK_TIMEOUT = float(os.environ.get("MUSKU_STUCK_TIMEOUT", "8.0"))
VOICE_STUCK_TIMEOUT_SPEAKING = float(os.environ.get("MUSKU_STUCK_SPEAKING", "10.0"))
GATE_WATCH_INTERVAL = float(os.environ.get("MUSKU_GATE_WATCH", "0.5"))

# --------------------------------------------------------------------------
# Ultra-fast profile — startup + hot-path overhead kam
# --------------------------------------------------------------------------
LIGHT_STARTUP = bool(int(os.environ.get(
    "MUSKU_LIGHT_STARTUP", "1" if INSTANT_VOICE_MODE else "0"
)))
LATENCY_TELEMETRY_ENABLED = bool(int(os.environ.get(
    "MUSKU_LATENCY_TELEM", "0" if INSTANT_VOICE_MODE else "1"
)))
LIGHT_UI_UPDATES = bool(int(os.environ.get(
    "MUSKU_LIGHT_UI", "0"
)))
MIC_MONITOR_DECIMATE = max(1, int(os.environ.get(
    "MUSKU_MIC_DECIMATE", "4" if INSTANT_VOICE_MODE else "1"
)))

# Gemini Live server VAD — user ke rukte hi turant reply (instant mode)
# Chhota silence_duration_ms = kam wait before Musku bolti hai
LIVE_SILENCE_DURATION_MS = int(os.environ.get(
    "MUSKU_SILENCE_MS", "220" if INSTANT_VOICE_MODE else "500"
))
LIVE_END_SPEECH_SENSITIVITY = os.environ.get("MUSKU_END_SPEECH_SENS", "high")
LIVE_START_SPEECH_SENSITIVITY = os.environ.get("MUSKU_START_SPEECH_SENS", "high")

USER_IDLE_CHECKIN_SECS = float(os.environ.get("MUSKU_IDLE_CHECKIN_SECS", "60"))
USER_IDLE_CHECKIN_COOLDOWN = float(os.environ.get("MUSKU_IDLE_CHECKIN_COOLDOWN", "120"))
USER_IDLE_CHECKIN_POLL = float(os.environ.get("MUSKU_IDLE_CHECKIN_POLL", "5"))

PROACTIVE_BREAK_MINS = int(os.environ.get("MUSKU_BREAK_MINS", "30"))
PROACTIVE_WATER_MINS = int(os.environ.get("MUSKU_WATER_MINS", "45"))
PROACTIVE_EYE_REST_MINS = int(os.environ.get("MUSKU_EYE_REST_MINS", "50"))
PROACTIVE_STRETCH_MINS = int(os.environ.get("MUSKU_STRETCH_MINS", "60"))
PROACTIVE_HEALTH_COOLDOWN = float(os.environ.get("MUSKU_HEALTH_COOLDOWN", "900"))

def get_transcription_language_code(language: str = "hinglish") -> str:
    """Pro mapping: Gemini Live input_audio_transcription language_code."""
    try:
        from language_policy import normalize_language
        lang = normalize_language(language or "hinglish")
    except Exception:
        lang = (language or "hinglish").lower()
    # env override
    env = (os.environ.get("MUSKU_TRANSCRIPTION_LANG") or "").strip()
    if env:
        return env
    if lang == "hindi":
        return "hi-IN"
    if lang == "english":
        return "en-IN"
    # hinglish best captured as hi-IN (handles Roman+Devanagari mix)
    return "hi-IN"

# --------------------------------------------------------------------------
def get_instant_voice_prompt(boss_name=None, language="hinglish", relationship_mode="best_friend"):
    """Minimal Live prompt — locked identity + pure conversational AI voice."""
    from personal_profile import get_locked_musku_prompt, LIVE_VOICE_RULES

    base = get_locked_musku_prompt(boss_name, language, relationship_mode=relationship_mode)
    from language_policy import get_language_persona_rules, normalize_language
    lang = normalize_language(language)
    extra_boundary = f"\n\n{POLITE_BOUNDARY_BLOCK.strip()}" if POLITE_BOUNDARY_BLOCK else ""
    return (
        base
        + "\n\n"
        + get_language_persona_rules(lang)
        + "\n\nSPEECH: Profile language follow karo. CHAT DISPLAY Roman Hinglish (hinglish mode) ya profile ke hisaab se.\n"
        + "CONVERSATIONAL BOUNDARY: Tum ek pure conversational AI assistant ho. Kisi computer/app/file ko control nahi kar sakti. Pura dhyaan user se baat karne, uski baaten samajhne aur yaad rakhne par rakho.\n"
        + "UPGRADE NOTE (typo bhi pakdo): User chahe 'image generate', 'imej janaret', 'kya tum image bana sakte ho', 'photo bana sakti ho' jaise SAAWAL bhi puche (chahe spelling galat ho) to bhi wahi professional upgrade note bolo — 'Jii [naam], jab S2 Sir mujhe upgrade karenge to ye function add kar denge, main is baat ko note kar rahi hu. 🥰'. Capability question ko normal answer mat samjho.\n"
        + LIVE_VOICE_RULES.strip()
        + extra_boundary
    )


def get_live_memory_block(uid=None):
    """Turn link + category facts + last 10 chats + rolling summary — Live prompt.
    Per-user scoped via explicit uid (falls back to current tenant context)."""
    turn_ctx = ""
    try:
        from memory import turn_context as _tctx
        turn_ctx = _tctx.get_live_turn_context_block(uid)
        _streak = _tctx.get_streak_prompt_block(uid)
    except Exception:
        turn_ctx = ""
        _streak = ""
    category_block = ""
    try:
        from memory.store import format_live_memory_card
        category_block = format_live_memory_card()
    except Exception:
        pass
    try:
        from memory import chat as chat_mem
        recent = chat_mem.load_recent_memory_context()
        summary = chat_mem.load_chat_summary()
    except Exception:
        recent = ""
        summary = ""
    parts = []
    # Previous-reply rule: user "ha batao" / "aage batao" / "continue karo" /
    # "kya bol rahi thi" bole to LAST MUSKU REPLY ka text WORD-FOR-WORD repeat
    # karna (answer beech me ruk gaya tha — wahi jawab poora sunna chahta hai).
    try:
        from memory import last_question as _lq
        _last_r = _lq.get_last_reply(uid)
        _last_q = _lq.get_last_question(uid)
    except Exception:
        _last_r = ""
        _last_q = ""
    prev_q_rule = (
        "PREVIOUS-REPLY RULE (sabse zaroori): Agar user ka naya message inme se "
        "koi ho — 'ha batao', 'phir se batao', 'dobara batao', 'answer do', "
        "'jawab do', 'continue karo', 'aage batao', 'kya bol rahi thi', "
        "'repeat karo', 'wahi batao', 'pichla question ka answer do' — to iska "
        "matlab pichhla answer beech me ruk gaya tha aur user WOHI jawab poora "
        "sunna chahta hai. SABSE PEHLE LAST MUSKU REPLY (neeche) ka text hi "
        "WORD-FOR-WORD repeat karo — wahi sentences, wahi words. Agar last reply "
        "na ho to LAST USER QUESTION ka poora, clear, fresh jawab do. Naya topic "
        "mat chhedo, 'kaunsa sawal?' mat puchho."
    )
    if _last_r:
        prev_q_rule += f"\nLAST MUSKU REPLY (isi ka text WORD-FOR-WORD repeat karo): \"{_last_r}\""
    elif _last_q:
        prev_q_rule += f"\nLAST USER QUESTION (isi ka jawab do): \"{_last_q}\""
    parts.append(prev_q_rule)
    if turn_ctx:
        parts.append(turn_ctx)
    if _streak:
        parts.append(_streak)
    if category_block:
        parts.append(category_block)
    if recent:
        parts.append(
            "RECENT CONVERSATIONS (last sessions — naturally yaad rakho, file mention mat karo):\n"
            + recent
        )
    if summary:
        parts.append("OLDER CHAT SUMMARY (purani baaton ka saar):\n" + summary)
    if parts:
        parts.append(
            "MEMORY RULES: Jab user puche 'last time kya kiya', 'yaad hai', 'pichhli baat', "
            "'hum kya kar rahe the' — upar ki history/facts se seedha jawab do. "
            "Guess mat karo; jo saved hai wahi bolo. Yaadein bilkul naturally lao — "
            "ek dost ki tarah casual tone me, examples ke hisaab se."
        )
    return "\n\n".join(parts)


def get_live_system_prompt(boss_name=None, language="hinglish", relationship_mode="best_friend", uid=None):
    """Persona + persisted last-10 memory + summary (per-user aware)."""
    base = get_live_persona_prompt(boss_name, language, relationship_mode=relationship_mode)
    mem = get_live_memory_block(uid)
    if mem:
        return base + "\n\n" + mem
    return base


def get_live_persona_prompt(boss_name=None, language="hinglish", relationship_mode="best_friend"):
    """Voice session prompt — instant slim or full persona (per-user aware)."""
    if INSTANT_VOICE_MODE:
        return get_instant_voice_prompt(boss_name, language, relationship_mode=relationship_mode)
    return get_dynamic_persona_prompt(boss_name, language, relationship_mode=relationship_mode)


def get_dynamic_persona_prompt(boss_name=None, language="hinglish", relationship_mode="best_friend"):
    from personal_profile import get_locked_musku_prompt, LIVE_VOICE_RULES, TTS_STYLE_INSTRUCTION
    from language_policy import get_language_persona_rules

    extra_boundary = f"\n\n{POLITE_BOUNDARY_BLOCK.strip()}" if POLITE_BOUNDARY_BLOCK else ""
    return (
        get_locked_musku_prompt(boss_name, language, relationship_mode=relationship_mode)
        + "\nUse the profile language strictly — see LANGUAGE LOCK below.\n"
        + "IMPORTANT: Hindi profile = Devanagari for TTS; Hinglish = Roman; English = pure English.\n"
        + "For text-to-speech handoff: " + TTS_STYLE_INSTRUCTION
        + "\n\n"
        + get_language_persona_rules(language)
        + "\n\n" + LIVE_VOICE_RULES.strip()
        + "\n- Web tools: openApplication, openWebsite, playYouTube, searchYouTube, "
        + "pauseMedia/playMedia/nextMedia/prevMedia/stopMedia, closeActiveApplication, "
        + "analyzeActiveApp, openWhatsAppWeb, sendWhatsAppMessage, sendWhatsAppMedia, "
        + "viewWhatsAppStatus, readWhatsAppMessages, searchGoogle, setVolume, "
        + "takeScreenshot, readScreen. "
        + "Fallback: execute_musku_command."
        + extra_boundary
    )

# Fallback for initial load
PERSONA_SYSTEM_PROMPT = get_live_persona_prompt()

# --------------------------------------------------------------------------
# Prebuilt voices (Gemini Live ke supported prebuilt voice names)
# User/default list — har ek test karke best choose hogi. Yahan voice list
# expand kar sakta hai; naam invent NAHI kare (SDK supported hi rahein).
# --------------------------------------------------------------------------
VOICES = [
    # Female / neutral choices — tous test ke liye
    "Kore",
    "Leda",
    "Orus",
    "Zephyr",
    "Puck",
    "Charon",
    "Fenrir",
    "Aoede"
]

# Default voice — config.json > env > Leda
def _load_default_voice():
    env_voice = os.environ.get("GEMINI_LIVE_VOICE", "").strip()
    if env_voice in VOICES:
        return env_voice
    try:
        cfg_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config.json",
        )
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            saved = str(data.get("musku_voice", "")).strip()
            if saved in VOICES:
                return saved
    except Exception:
        pass
    return "Aoede"


DEFAULT_VOICE = _load_default_voice()

# --------------------------------------------------------------------------
# Test script (Phase 2 UI me editable) — voice comparison ke liye same sentences
# --------------------------------------------------------------------------
TEST_SENTENCES = [
    "Hello, main Musku hoon. Main aapki help karne ke liye ready hoon.",
    "Achha, bataiye aaj aap kya karna chahte hain?",
    "Haan, samajh gayi. Chalo, main aapki help karti hoon.",
    "Ek minute, main check karti hoon.",
]

# Reconnect / resume policy (session_resume.py isse padhta hai)
RECONNECT_BACKOFF = [1.0, 2.0, 4.0, 8.0, 15.0]   # seconds, max attempts len()
MAX_RECONNECT_ATTEMPTS = len(RECONNECT_BACKOFF)
# Backoff khatam hone ke baad slow fixed retry (client.py) — session kabhi
# permanently give-up nahi karta, continuous conversation bina restart ke
# apne aap resume hoti hai.
RECONNECT_SLOW_DELAY = 15.0   # seconds, slow-recovery mode interval

# Live connect network preflight (client.py `_network_ready`):
GEMINI_LIVE_HOST = "generativelanguage.googleapis.com"
NETWORK_PREFLIGHT_ENABLED = bool(int(os.environ.get("MUSKU_NETWORK_PREFLIGHT", "1")))
RECONNECT_PREFLIGHT_TIMEOUT = 4.0   # TCP connect timeout (s)
RECONNECT_PREFLIGHT_RETRY = 2.0     # preflight fail hone ke baad retry gap (s)
PREFLIGHT_BYPASS_AFTER = 2          # itni fail ke baad SDK connect direct try

# Long conversation ke liye (context_compression.py)
COMPRESSION_WINDOW_TURNS = 24        # itne turns ke baad older ko summarize karo
COMPRESS_KEEP_RECENT_TURNS = 6
COMPRESSION_MODEL = DEFAULT_MODEL     # summary ke liye use hota hai (text)
