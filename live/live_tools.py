"""live_tools.py — Pure Conversational Tool Declarations & Routing for MUSKU 2.0.

Gemini Live tools are strictly restricted to safe conversational functionality:
- saveMemory: Save user profile/preferences facts into long-term Firestore/local memory
- searchWebInfo: Pure informational web search (returns knowledge summary to model, NEVER controls browser)

All PC, browser, application, system, media, window, file, WhatsApp, and OS automation tool declarations
have been completely removed.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple, List

try:
    from google.genai import types
    _HAVE_GENAI = True
except ImportError:
    _HAVE_GENAI = False
    types = None  # type: ignore


LIVE_TOOL_ROUTES: Dict[str, Tuple[str, Callable[[dict], dict]]] = {
    "saveMemory": ("save_memory", lambda a: {"fact": a.get("fact") or a.get("memory") or "", "category": a.get("category") or "general"}),
    "searchWebInfo": ("web_search", lambda a: {"query": a.get("query") or ""}),
}


def resolve_live_tool(name: str, args: dict) -> Tuple[Optional[str], dict]:
    """Resolves Gemini Live tool call into (intent_name, normalized_dict).
    Guaranteed NEVER to return any PC/OS control intent.
    """
    route = LIVE_TOOL_ROUTES.get(name)
    if not route:
        return None, {}
    intent, normalizer = route
    return intent, normalizer(args or {})


def build_function_declarations(use_live_tools: bool = True, slim: bool = False) -> List[Any]:
    """Returns pure conversational FunctionDeclarations for Gemini Live."""
    if not _HAVE_GENAI or not types or not use_live_tools:
        return []

    tools_list = []

    try:
        # 1. saveMemory
        save_memory_decl = types.FunctionDeclaration(
            name="saveMemory",
            description="Save a new long-term memory or user preference fact (e.g. user's favorite food, name, passion).",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "fact": types.Schema(type=types.Type.STRING, description="The key fact or user preference to remember."),
                    "category": types.Schema(type=types.Type.STRING, description="Category: 'preferences', 'relations', 'tasks', or 'general'."),
                },
                required=["fact"],
            ),
        )
        tools_list.append(save_memory_decl)

        # 2. searchWebInfo
        search_web_decl = types.FunctionDeclaration(
            name="searchWebInfo",
            description="Search the web for real-time information, weather, or news to answer user's question.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query": types.Schema(type=types.Type.STRING, description="The search query."),
                },
                required=["query"],
            ),
        )
        tools_list.append(search_web_decl)
    except Exception:
        pass

    return tools_list
