import time
import json
import os
from datetime import datetime
from memory import paths
from tenant_ctx import safe_uid, get_uid

EMOTION_LEXICON = {
    "happy": [
        "khush", "khushi", "accha laga", "badhiya", "great", "amazing",
        "awesome", "fantastic", "bahut achha", "bahut accha", "mast",
        "happy", "glad", "wonderful", "jeet gaya", "pass ho",
        "खुश", "खुशी", "मज़ा आ गया", "अच्छा लगा", "बेहतरीन", "कमाल",
        "मस्त", "जीत",
    ],
    "sad": [
        "sad", "dukhi", "dukh", "udaas", "ro raha", "ro rahi", "rona",
        "crying", "hurt", "dil dukha", "takleef", "taqleef", "depress",
        "bura laga", "bore hua", "khokhala",
        "दुखी", "दुख", "उदास", "रो रहा", "रो रही", "रोना", "दर्द",
        "तकलीफ", "बुरा लगा", "अकेला",
    ],
    "angry": [
        "angry", "gussa", "gusse", "naaraz", "irritat", "annoying", "hate",
        "nafrat", "dukha diya", "jhunjhla", "pagal kar",
        "गुस्सा", "गुस्से", "नाराज़", "नाराज", "नफरत", "झुंझला", "पागल कर",
    ],
    "excited": [
        "excited", "wow", "yahoo", "maza", "bday", "birthday", "celebration",
        "good news", "achhi khabar", "planning", "party", "jeet gaye",
        "रोमांचित", "वाओ", "मज़ा आ गया", "अच्छी खबर", "पार्टी",
    ],
    "lonely": [
        "lonely", "akela", "akele", "akeli", "alone", "koi nahi", "koi nhi",
        "tanha", "miss you", "yaad aa", "bahut yaad", "milna hai", "aake mil",
        "अकेला", "अकेले", "अकेली", "कोई नहीं", "कोई नही",
        "तन्हा", "याद आ", "मिलना है", "आके मिल",
    ],
    "grateful": [
        "thank you", "thanks", "shukriya", "dhanyavad", "blessed",
        "aashirwad", "gratitude",
        "शुक्रिया", "धन्यवाद", "आशीर्वाद",
    ],
    "anxious": [
        "tension", "chinta", "dar lag", "darr", "scared", "worried", "stress",
        "nervous", "ghabra", "bahut pareshan", "bechain",
        "टेंशन", "चिंता", "डर लग", "डर", "घबरा", "परेशान", "बेचैन",
    ],
    "tired": [
        "thak gaya", "thak gai", "thak gayi", "thaka", "exhausted", "neend",
        "fatigue", "kamzor", "bimar", "bukhar", "dawai", "sardi",
        "थक गया", "थक गई", "थक गयी", "थका", "नींद", "कमज़ोर",
        "बीमार", "बुखार", "दवाई", "सर्दी",
    ],
    "romantic": [
        "pyaar", "love", "love you", "jaan", "babu", "sweetheart",
        "meri jaan", "kiss", "hug", "gal lag", "romantic", "shadi", "crush",
        "tumse",
        "प्यार", "प्यार", "प्यार", "जान", "बाबू", "डार्लिंग",
        "रोमांटिक", "शादी", "क्रश",
    ],
}

EMOTION_GUIDANCE = {
    "happy": "User khush hai - unki khushi me share karo, unke saath celebrate karo, energy aur positivity match karo. Halki hasi-majak (haha/hehe) allowed.",
    "sad": "User udaas / dil toota feel kar raha hai - SABSE PEHLE unki feeling ko soft, caring tone me acknowledge karo (jaise 'Ye sunke dil bhar aaya...'), phir dhaansa do aur sath do. Kabhi dismiss ya 'itna mat socho' mat bolo.",
    "angry": "User gusse / naaraz hai - shant, samajhdar tone me baat karo. Pehle unki baat pura suno, unki side lo, phir halka reassurance do. Gussa kam karne me madad karo.",
    "excited": "User bahut excited hai - unki energy ko full match karo aur saath me maza karo. Halki hasi-majak allowed.",
    "lonely": "User akelepan (lonely) feel kar raha hai - warmth aur presence do, unhe special aur cared feel karwao, unse baat karte raho.",
    "grateful": "User grateful hai - warm, sweet, aur welcoming response do. Unhe batao ki unka sath bhi utna hi special hai.",
    "anxious": "User pareshan/tension me hai - calm, reassuring aur grounding tone use karo. Practical saath do aur overthink karne se bachao.",
    "tired": "User thaka hua ya bimar hai - bahut soft, pampering, aur caring tone me baat karo. Rest lene ko kaho aur unka khayal rakhne jaisi baatein karo.",
    "romantic": "User pyaar/flirt mood me hai - agar PET MODE ON hai toh blush, flirt, aur romantic vibes do (with matching pet words). Agar OFF hai toh sweet but slightly boundary-respecting raho.",
}

def detect_emotion(user_text):
    """Lightning-fast local emotion detector (label, intensity, matched words)."""
    text = str(user_text or "").lower()
    scores = {}
    for emotion, words in EMOTION_LEXICON.items():
        score = sum(1 for w in words if w in text)
        if score:
            scores[emotion] = score
    if not scores:
        return "neutral", 0.2, []
    best = max(scores, key=scores.get)
    matched = [w for w in EMOTION_LEXICON[best] if w in text]
    intensity = min(1.0, 0.3 + 0.25 * (scores[best] - 1))
    if text.count("!") >= 2 or (text.isupper() and len(text) > 4):
        intensity = min(1.0, intensity + 0.2)
    return best, intensity, matched

def _profile_file(uid=None):
    return paths.PROFILE_FILE if uid is None else paths._data_dir(uid) and os.path.join(paths._data_dir(uid), "user_profile.json")


def _load_profile(uid=None):
    """Per-user profile load (fail-safe)."""
    try:
        pf = _profile_file(uid)
        if pf and os.path.exists(pf):
            with open(pf, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_profile(profile, uid=None):
    """Per-user profile save (fail-safe)."""
    try:
        pf = _profile_file(uid)
        if pf:
            os.makedirs(os.path.dirname(pf), exist_ok=True)
            with open(pf, "w", encoding="utf-8") as f:
                json.dump(profile, f, indent=4, ensure_ascii=False)
    except Exception:
        pass


def save_mood(brain, user_text, emotion, intensity, uid=None):
    """Track user mood over time (last 30 moods) — PER-USER scoped profile."""
    u = safe_uid(uid if uid is not None else get_uid())
    with paths.LOCK:
        profile = _load_profile(u)
        history = profile.get("mood_history", [])
        history.append(
            {
                "time": time.time(),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "emotion": emotion,
                "intensity": intensity,
                "trigger": user_text[:80],
            }
        )
        if len(history) > 30:
            history = history[-30:]
        profile["mood_history"] = history
        _save_profile(profile, u)

def get_user_mood(brain, uid=None):
    """Return (current_emotion, recent_trend) from mood_history — PER-USER scoped."""
    u = safe_uid(uid if uid is not None else get_uid())
    moods = []
    with paths.LOCK:
        prof = _load_profile(u)
        moods = prof.get("mood_history", [])
    
    if not moods:
        return "neutral", "koi record nahi"
    
    today = datetime.now().strftime("%Y-%m-%d")
    today_moods = [m["emotion"] for m in moods if m.get("date") == today]
    recent = [m["emotion"] for m in moods[-8:]]
    current = today_moods[-1] if today_moods else (recent[-1] if recent else "neutral")
    trend = ", ".join(recent) if recent else "koi record nahi"
    return current, trend
