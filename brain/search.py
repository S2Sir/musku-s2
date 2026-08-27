import re
import os
import time

FOLLOWUP_SEARCH_PHRASES = (
    "search nahi kiya", "search kiya nahi", "search abhi tak", "search karo abhi",
    "abhi tak nahi", "result kahan", "kya hua search", "search hua kya",
)

def web_search(query):
    """Live Web Search - SIRF Google (browser).
    Provider: CDP Chrome scrape (free, no API key). Fail -> (None, None)."""
    from musku_tools import web_search as gws
    summary, results = gws.search(query)
    if summary and results:
        return summary, results
    return None, None

def is_follow_up_search(brain, text):
    """User last search ka result/status puch raha hai (naye topic nahi)?
    Sirf tab True agar last search <=15 min purana ho (recent context)."""
    if not brain._last_search_query:
        return False
    if time.time() - brain._last_search_at > 900:  # 15 min
        return False
    t = re.sub(r"\s+", " ", str(text or "")).lower()
    return any(ph in t for ph in FOLLOWUP_SEARCH_PHRASES)
