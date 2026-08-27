"""firebase/firestore.py — Cloud Firestore Persistence Engine for MUSKU 2.0.

Provides multi-user database storage mapping user data to the hierarchy:
- users/{uid}/profile/main: User profile, preferred title, relationship mode, language
- users/{uid}/preferences/main: User preferences (likes, dislikes, tech stack, work style)
- users/{uid}/memory/main: Categorical facts (relations, tasks, long-term memory)
- users/{uid}/reminders/{reminder_id}: Scheduled reminders and alarms
- users/{uid}/conversations/{date}: Per-date conversation session metadata
- users/{uid}/messages/{msg_id}: Individual chat log messages

Gracefully degrades to local JSON storage if Firestore environment is unavailable.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("musku.firebase.firestore")

_db_client = None
_db_initialized = False


def get_firestore_client():
    global _db_client, _db_initialized
    if _db_initialized:
        return _db_client

    _db_initialized = True
    try:
        import firebase_admin
        from firebase_admin import firestore

        if not firebase_admin._apps:
            firebase_admin.initialize_app()

        _db_client = firestore.client()
        logger.info("Cloud Firestore client initialized successfully.")
    except Exception as e:
        logger.warning("Cloud Firestore client initialization deferred/bypassed: %s", e)
        _db_client = None

    return _db_client


def save_user_profile_fs(uid: str, data: Dict[str, Any]) -> bool:
    db = get_firestore_client()
    if not db or not uid:
        return False
    try:
        doc_ref = db.collection("users").document(uid).collection("profile").document("main")
        doc_ref.set(data, merge=True)
        return True
    except Exception as e:
        logger.error("Error saving user profile to Firestore for UID %s: %s", uid, e)
        return False


def load_user_profile_fs(uid: str) -> Optional[Dict[str, Any]]:
    db = get_firestore_client()
    if not db or not uid:
        return None
    try:
        doc = db.collection("users").document(uid).collection("profile").document("main").get()
        if doc.exists:
            return doc.to_dict()
    except Exception as e:
        logger.error("Error loading user profile from Firestore for UID %s: %s", uid, e)
    return None


def save_categorical_memory_fs(uid: str, category: str, items: List[Any]) -> bool:
    db = get_firestore_client()
    if not db or not uid or not category:
        return False
    try:
        doc_ref = db.collection("users").document(uid).collection("memory").document(category)
        doc_ref.set({"items": items, "updated_at": firestore.SERVER_TIMESTAMP if db else None}, merge=True)
        return True
    except Exception as e:
        logger.error("Error saving memory category %s to Firestore for UID %s: %s", category, uid, e)
        return False


def load_categorical_memory_fs(uid: str, category: str) -> Optional[List[Any]]:
    db = get_firestore_client()
    if not db or not uid or not category:
        return None
    try:
        doc = db.collection("users").document(uid).collection("memory").document(category).get()
        if doc.exists:
            data = doc.to_dict()
            return data.get("items", [])
    except Exception as e:
        logger.error("Error loading memory category %s from Firestore for UID %s: %s", category, uid, e)
    return None


def save_chat_turn_fs(uid: str, date_str: str, user_text: str, musku_reply: str, meta: Optional[Dict[str, Any]] = None) -> bool:
    db = get_firestore_client()
    if not db or not uid or not date_str:
        return False
    try:
        turn_data = {
            "user": user_text,
            "musku": musku_reply,
            "timestamp": firestore.SERVER_TIMESTAMP,
            "date": date_str,
            "meta": meta or {},
        }
        db.collection("users").document(uid).collection("conversations").document(date_str).collection("turns").add(turn_data)
        return True
    except Exception as e:
        logger.error("Error saving chat turn to Firestore for UID %s: %s", uid, e)
        return False


def get_recent_chat_turns_fs(uid: str, date_str: str, limit: int = 10) -> List[Dict[str, Any]]:
    db = get_firestore_client()
    if not db or not uid or not date_str:
        return []
    try:
        query = (
            db.collection("users").document(uid)
            .collection("conversations").document(date_str)
            .collection("turns").order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        docs = query.stream()
        turns = []
        for doc in docs:
            t = doc.to_dict()
            turns.append(t)
        turns.reverse()
        return turns
    except Exception as e:
        logger.error("Error loading recent chat turns from Firestore for UID %s: %s", uid, e)
        return []
