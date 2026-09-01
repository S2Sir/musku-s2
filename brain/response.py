import re
import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "musku_data")

# ---------------------------------------------------------------------------
# PET WORDS STRIP
# ---------------------------------------------------------------------------
_BLOCKED_PET_WORDS = set()
_PET_WORDS_FILE = os.path.join(DATA_DIR, "blocked_pet_words.txt")
try:
    with open(_PET_WORDS_FILE, "r", encoding="utf-8") as f:
        _BLOCKED_PET_WORDS = {line.strip().lower() for line in f if line.strip()}
except Exception:
    pass

def _strip_pet_words(text, pet_mode_active):
    """Strip blocked pet words from text when PET MODE is not active."""
    if pet_mode_active or not text:
        return text
    for word in sorted(_BLOCKED_PET_WORDS, key=lambda w: len(w), reverse=True):
        pattern = rf"\b{re.escape(word)}\b"
        text = re.sub(pattern, "", text, flags=re.I)
    text = re.sub(r"[,\s]+,[,\s]*", ", ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

# ---------------------------------------------------------------------------
# GRAMMAR AND GENDER FIXES
# ---------------------------------------------------------------------------
_GRAMMAR_FIXES = None

def _load_grammar_fixes():
    global _GRAMMAR_FIXES
    if _GRAMMAR_FIXES is None:
        try:
            path = os.path.join(DATA_DIR, "grammar_fixes.json")
            with open(path, "r", encoding="utf-8-sig") as f:
                _GRAMMAR_FIXES = json.load(f)
        except Exception as e:
            print(f"[Grammar Fixes Load Error]: {e}")
            _GRAMMAR_FIXES = {"devanagari": {}}
    return _GRAMMAR_FIXES

def _grammar_fix(text, lang="devanagari"):
    if not text:
        return text
    fixes = _load_grammar_fixes().get(lang, {})
    for wrong, right in fixes.items():
        if wrong not in text:
            continue
        text = re.sub(
            rf"(?<![\u0900-\u097f]){re.escape(wrong)}(?![\u0900-\u097f])",
            right,
            text,
        )
    return text

def _fix_roman_gender(text):
    text = re.sub(r"\bgaya\s+tha\b", "gayi thi", text, flags=re.I)
    text = re.sub(r"\bmain\s+tha\b", "main thi", text, flags=re.I)
    text = re.sub(r"\bmai[nN]\s+gaya\b", "main gayi", text, flags=re.I)
    text = re.sub(r"\bmai[nN]\s+aya\b", "main aayi", text, flags=re.I)
    text = re.sub(r"\bmai[nN]\s+soya\b", "main soyi", text, flags=re.I)
    text = re.sub(r"\bkarunga\b", "karungi", text, flags=re.I)
    text = re.sub(r"\bkarta\s+hun\b", "karti hun", text, flags=re.I)
    text = re.sub(r"\bkarta\s+hai\b", "karti hai", text, flags=re.I)
    text = re.sub(r"\bbolta\s+hun\b", "bolti hun", text, flags=re.I)
    text = re.sub(r"\bdeta\s+hun\b", "deti hun", text, flags=re.I)
    text = re.sub(r"\baata\s+hu\b", "aati hun", text, flags=re.I)
    text = re.sub(r"\baata\s+hun\b", "aati hun", text, flags=re.I)
    text = re.sub(r"\bmai[nN]\s+(?:soya|khaya|chala|bola|suna|gaya|aaya)\b",
                  lambda m: m.group(0).replace("soya", "soyi").replace("khaya", "khayi")
                  .replace("chala", "chali").replace("bola", "boli")
                  .replace("suna", "suni").replace("gaya", "gayi").replace("aaya", "aayi"),
                  text, flags=re.I)
    return text

def _fix_deva(text, pet_mode_active):
    if not text:
        return text
    text = _grammar_fix(text, lang="devanagari")
    text = re.sub(r"ऊँगा", "ऊँगी", text)
    text = re.sub(r"मैं गया(?![\u0900-\u097F])", "मैं गई", text)
    text = re.sub(r"मैं आया(?![\u0900-\u097F])", "मैं आई", text)
    text = re.sub(r"मैं सोया(?![\u0900-\u097F])", "मैं सोई", text)
    text = re.sub(r"मैं खा लिया(?![\u0900-\u097F])", "मैं खा ली", text)
    text = re.sub(r"मैं चला(?![\u0900-\u097F])", "मैं चली", text)
    text = re.sub(r"मैं बोला(?![\u0900-\u097F])", "मैं बोली", text)
    text = re.sub(r"मैं दिया(?![\u0900-\u097F])", "मैं दी", text)
    text = re.sub(r"मैं लिया(?![\u0900-\u097F])", "मैं ली", text)
    text = re.sub(r"मैं पाया(?![\u0900-\u097F])", "मैं पाई", text)
    text = re.sub(r"मैं सुना(?![\u0900-\u097F])", "मैं सुनी", text)
    text = re.sub(r"मैं बताया(?![\u0900-\u097F])", "मैं बताई", text)
    text = re.sub(r"मैं देखा(?![\u0900-\u097F])", "मैं देखी", text)
    text = re.sub(r"मैं था(?![\u0900-\u097F])", "मैं थी", text)
    text = re.sub(r"करता हूँ", "करती हूँ", text)
    text = re.sub(r"करता है", "करती है", text)
    text = re.sub(r"बोलता हूँ", "बोलती हूँ", text)
    text = re.sub(r"बोलता है", "बोलती है", text)
    text = re.sub(r"देता हूँ", "देती हूँ", text)
    text = re.sub(r"देता है", "देती है", text)
    text = re.sub(r"लेता हूँ", "लेती हूँ", text)
    text = re.sub(r"लेता है", "लेती है", text)
    text = re.sub(r"पढ़ता हूँ", "पढ़ती हूँ", text)
    text = re.sub(r"पढ़ता है", "पढ़ती है", text)
    text = re.sub(r"समझता हूँ", "समझती हूँ", text)
    text = re.sub(r"समझता है", "समझती है", text)
    text = re.sub(r"जाता हूँ", "जाती हूँ", text)
    text = re.sub(r"जाता है", "जाती है", text)
    text = re.sub(r"आता हूँ", "आती हूँ", text)
    text = re.sub(r"आता है", "आती है", text)
    text = re.sub(r"रहता हूँ", "रहती हूँ", text)
    text = re.sub(r"रहता है", "रहती है", text)
    text = re.sub(r"खाता हूँ", "खाती हूँ", text)
    text = re.sub(r"खाता है", "खाती है", text)
    text = re.sub(r"पीता हूँ", "पीती हूँ", text)
    text = re.sub(r"पीता है", "पीती है", text)
    text = re.sub(r"सोता हूँ", "सोती हूँ", text)
    text = re.sub(r"सोता है", "सोती है", text)
    text = re.sub(r"करते हो", "करती हो", text)
    text = re.sub(r"बोलते हो", "बोलती हो", text)
    text = re.sub(r"देते हो", "देती हो", text)
    text = re.sub(r"लेते हो", "लेती हो", text)
    text = re.sub(r"पढ़ते हो", "पढ़ती हो", text)
    text = re.sub(r"समझते हो", "समझती हो", text)
    text = re.sub(r"जाते हो", "जाती हो", text)
    text = re.sub(r"आते हो", "आती हो", text)
    text = re.sub(r"रहते हो", "रहती हो", text)
    text = re.sub(r"खाते हो", "खाती हो", text)
    text = re.sub(r"सोते हो", "सोती हो", text)
    text = re.sub(r"हो गया", "हो गई", text)
    text = re.sub(r"हो गयी", "हो गई", text)
    text = re.sub(r"गया था(?![\u0900-\u097F])", "गई थी", text)
    text = re.sub(r"गया(?![\u0900-\u097F])", "गई", text)
    text = re.sub(r"गई था(?![\u0900-\u097F])", "गई थी", text)
    text = re.sub(r"आया(?![\u0900-\u097F])", "आई", text)
    text = re.sub(r"सोया(?![\u0900-\u097F])", "सोई", text)
    text = re.sub(r"खाया(?![\u0900-\u097F])", "खाई", text)
    text = re.sub(r"चला(?![\u0900-\u097F])", "चली", text)
    text = re.sub(r"बोला(?![\u0900-\u097F])", "बोली", text)
    text = re.sub(r"दिया(?![\u0900-\u097F])", "दी", text)
    text = re.sub(r"लिया(?![\u0900-\u097F])", "ली", text)
    text = re.sub(r"पाया(?![\u0900-\u097F])", "पाई", text)
    text = re.sub(r"सुना(?![\u0900-\u097F])", "सुनी", text)
    text = re.sub(r"बताया(?![\u0900-\u097F])", "बताई", text)
    text = re.sub(r"देखा(?![\u0900-\u097F])", "देखी", text)
    text = _strip_pet_words(text, pet_mode_active)
    text = re.sub(r"[,\s]+,[,\s]*", ", ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def finalize_reply(text, language, pet_mode_active):
    try:
        from personal_profile import enforce_musku_identity
    except Exception:
        try:
            from brain_core import enforce_boss_tone as enforce_musku_identity
        except Exception:
            enforce_musku_identity = lambda x, **kwargs: x

    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return text
    if language == "hindi" or re.search(r"[\u0900-\u097F]", text):
        text = _fix_deva(text, pet_mode_active)
    else:
        text = _strip_pet_words(text, pet_mode_active)
        text = _fix_roman_gender(text)
    return enforce_musku_identity(text, pet_mode=pet_mode_active)
