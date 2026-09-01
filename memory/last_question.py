# memory/last_question.py - "Pichla question ka answer do" handling.
#
# Scenario: User sawal puchta hai -> Musku answer dena shuru karti hai -> beech
# me ruk jata hai. User phir kehta hai "ha batao" / "pichla question ka answer
# do". Isse Musku ko last user question ka POORA, fresh answer dena chahiye —
# naya topic nahi.
#
# Ye module:
#   - detect_previous_question_request(text): kya user previous-question answer
#     mang raha hai (Hinglish + Devanagari).
#   - get_last_question(): turn_context / history se last USER question wapas.
#   - build_previous_question_instruction(last_q): system-prompt block.
import re

from . import turn_context


def _normalize(text):
    return re.sub(r"\s+", " ", str(text or "")).lower().strip()


# Strong intents — apne aap previous-question ka reference dete hain.
_STRONG_INTENT_PATTERNS = (
    # Hinglish
    "pichla question", "pichhla question", "pichle question", "pichhle question",
    "pichla sawal", "pichhla sawal", "pichle sawal", "pichhle sawal",
    "pichla prashn", "pichhla prashn",
    "pichla wala", "pichhla wala", "pichle wala", "pichhle wala",
    "pichla jawab", "pichhla jawab", "pichla answer",
    "wahi sawal", "wahi question", "wahi wala sawal", "wahi wala question",
    "previous question", "last question",
    "purana sawal", "purane sawal", "purana question", "purane question",
    # Devanagari
    "पिछला सवाल", "पिछले सवाल", "पिछला प्रश्न", "पिछले प्रश्न",
    "पिछला वाला", "पिछले वाला", "पिछला जवाब", "पिछला उत्तर",
    "वही सवाल", "वही वाला सवाल", "पुराना सवाल", "पुराने सवाल",
)

# Answer-request verbs — "answer/jawab do" type (sirf jab last question maujood ho).
_ANSWER_REQUEST_PATTERNS = (
    "answer do", "answer batao", "answer btao", "answer de", "answer dijiye",
    "jawab do", "jawab batao", "jawab de", "jawab btao", "jawab dijiye",
    "uttar do", "uttar batao",
    "जवाब दो", "जवाब बताओ", "जवाब दीजिए", "उत्तर दो", "उत्तर बताओ",
)

# Continue phrases — beech me rukne ke baad "aage batao" type (last question chahiye).
_CONTINUE_PATTERNS = (
    "ha batao", "haan batao", "ha btao", "haan btao",
    "ha bolo", "haan bolo",
    "batao na", "bata na", "batana",
    "phir se batao", "phir se btao", "phir se bolo", "fir se batao", "fir se bolo",
    "dobara batao", "dobara bolo", "dubara batao", "dubara bolo",
    "continue karo", "continue kro", "continue",
    "aage batao", "aage bolo", "aage ka batao", "aage sunao",
    "wahi batao", "wahi bolo", "wahi bol",
    "pura batao", "poora batao", "complete batao",
    "bas wahi batao", "bas wahi jawab",
    "kya bol rahi thi", "kya boli thi", "kya keh rahi thi", "kya boli",
    "kya bol rahe the", "kya keh rahe the",
    "repeat karo", "repeat kro", "repeat", "repeat karke batao",
    "phir se sunao", "dobara sunao", "dubara sunao", "wahi sunao",
    "kahan ruki thi", "kahan ruk gayi", "beech me hi", "aadha batao",
    "पूरा बताओ", "पूरा बोलो", "रिपीट करो", "रिपीट करके बताओ",
    "क्या बताया था", "क्या कह रही थी",
    "हाँ बताओ", "हाँ बोलो", "फिर से बताओ", "फिर से बोलो",
    "दोबारा बताओ", "दोबारा बोलो", "आगे बताओ", "आगे बोलो", "आगे सुनाओ",
    "वही बताओ", "जारी रखो", "बता ना", "बताओ ना", "पूरा बताओ",
)

_QUESTION_WORDS = (
    "kya", "kaun", "kaise", "kese", "kaisa", "kaisi", "kab", "kahan", "kaha",
    "kitna", "kitne", "kitni", "kyu", "kyun", "kyo", "kis", "konsa", "konse",
    "kaunsa", "kaunse", "batao", "btao", "bataiye", "sunao", "bolo", "bol",
    "define", "meaning", "matalab", "matlab", "bata do", "bol do",
    "क्या", "कौन", "कैसे", "कैसा", "कैसी", "कब", "कहाँ", "कितना", "कितने",
    "क्यों", "किस", "कौनसा", "कौनसे", "बताओ", "बताइए", "सुनाओ", "बोलो",
)


def _looks_like_question(text):
    """Kya ye message sawal jaisa hai?"""
    if not text:
        return False
    if "?" in text:
        return True
    low = text.lower()
    return any(w in low for w in _QUESTION_WORDS)


def detect_previous_question_request(user_text):
    """User previous-question ka answer mang raha hai ya nahi."""
    text = _normalize(user_text)
    if not text:
        return False
    if any(p in text for p in _STRONG_INTENT_PATTERNS):
        return True
    # Continue/answer-request phrases sirf tab hijack karte hain jab ek last
    # question actually saved hai — warna normal flow (false-positive guard).
    if any(p in text for p in _ANSWER_REQUEST_PATTERNS) or any(
        p in text for p in _CONTINUE_PATTERNS
    ):
        return bool(get_last_question())
    return False


def get_last_question(uid=None):
    """Turn-context se last USER question wapas (fallback: recent turns ring).
    Sirf sawal jaisa last message hi return hota hai — commands ('gaana chalao')
    kabhi previous-question nahi banenge. Agar last_user koi command hai (empty
    nahi), to purane ring se hijack nahi karte. Per-user scoped."""
    try:
        snap = turn_context.snapshot(uid)
        last_user = (snap.get("last_user") or "").strip()
    except Exception:
        last_user = ""
    if _looks_like_question(last_user):
        return last_user[:500]
    if last_user:
        return ""
    try:
        from . import chat as _mchat
        for e in reversed(_mchat.load_recent_turns_ring()):
            u = (e.get("user_said") or "").strip()
            if _looks_like_question(u):
                return u[:500]
    except Exception:
        pass
    return ""


def build_previous_question_instruction(last_question):
    """System-prompt block — user previous-question ka answer mang raha hai."""
    block = (
        "PREVIOUS-QUESTION RULE (sabse zaroori - abhi ka turn): User abhi keh raha "
        "hai ki pichhla sawal ka jawab do / answer batao. Iska matlab: Musku ka "
        "pichhla answer beech me ruk gaya tha, aur user wahi jawab poora chahta hai. "
        "NIECHE diye gaye sawal ka hi poora, clear, fresh jawab do. Naya topic mat "
        "chhedo, 'kaunsa sawal?' mat puchho, kuch aur mat bolo."
    )
    if last_question:
        block += f"\nLAST USER QUESTION (isi ka jawab do): \"{last_question}\""
    return block


def get_last_reply(uid=None):
    """Musku ka last spoken reply (complete ya interrupted partial) — verbatim
    repeat ke liye. turn_context.last_musku se aata hai — wahi text jo beech me
    ruk gayi thi ya poora bola gaya. Per-user scoped."""
    try:
        snap = turn_context.snapshot(uid)
        return (snap.get("last_musku") or "").strip()[:800]
    except Exception:
        return ""


def build_last_reply_instruction(last_reply):
    """System-prompt block — user 'aage batao' / 'continue' bolke WOHI pichhla
    reply repeat karwana chahta hai (na ki naya fresh answer)."""
    block = (
        "REPEAT-LAST-REPLY RULE (sabse zaroori - abhi ka turn): User abhi keh raha "
        "hai 'ha batao' / 'aage batao' / 'continue karo' / 'kya bol rahi thi'. "
        "Iska matlab: Musku ka pichhla jawab beech me ruk gaya tha, aur user WOHI "
        "jawab dobara/poore sunna chahta hai. Neeche diya LAST MUSKU REPLY ka text "
        "hi WORD-FOR-WORD repeat karo — wahi sentences, wahi words. Naya fresh "
        "answer mat banao, topic mat badlo, kuch aur mat jodo."
    )
    if last_reply:
        block += f"\nLAST MUSKU REPLY (isi ka text WORD-FOR-WORD repeat karo): \"{last_reply}\""
    return block
