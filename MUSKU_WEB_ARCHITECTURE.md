# 🧠 MUSKU 2.0 — WEB CONVERSATIONAL AI MASTER ARCHITECTURE MANUAL

> **Authoritative Specification:** This document provides the 100% complete, up-to-date architectural manual for **MUSKU 2.0** — a pure, production-grade **Web-based Conversational AI Female Assistant** (Realtime Voice + Text + Firebase Auth + Cloud Firestore + Cloud Run / Firebase Hosting deployment).

---

## 📑 TABLE OF CONTENTS
1. [Product Purpose & Strict Boundary](#1-product-purpose--strict-boundary)
2. [Production Network & Deployment Architecture](#2-production-network--deployment-architecture)
3. [Exhaustive Directory & File Map](#3-exhaustive-directory--file-map)
4. [5-Authority Persona Engine](#4-5-authority-persona-engine)
5. [Multi-User Identity & Cloud Firestore Storage Engine](#5-multi-user-identity--cloud-firestore-storage-engine)
6. [Realtime Gemini Live Voice & Audio Engine](#6-realtime-gemini-live-voice--audio-engine)
7. [Pure Conversational Intent Router & Safe Tools](#7-pure-conversational-intent-router--safe-tools)
8. [Testing & Verification Suite](#8-testing--verification-suite)

---

## 1. PRODUCT PURPOSE & STRICT BOUNDARY

MUSKU 2.0 is a **conversational AI female assistant** designed for talking with the user through voice and text.

### Core Capabilities
- Realtime voice conversation with native 24kHz **`Aoede`** AI female voice.
- Direct Web Audio playback and microphone 16kHz PCM streaming.
- Realtime barge-in / speech interruption handling.
- Text chat with deep conversation context and follow-up question solving.
- 5-Authority Persona adaptation (Best Friend, Beti, Caring, Girlfriend, Jigri).
- Multi-user data isolation via Firebase Authentication ID tokens.
- Categorical long-term personal memory backed by Cloud Firestore.

### Absolute Security Boundary
MUSKU 2.0 contains **ZERO computer control, desktop automation, or OS control capabilities**.
- MUSKU CANNOT open, close, or switch applications.
- MUSKU CANNOT control mouse, keyboard, or desktop windows.
- MUSKU CANNOT execute local scripts, Python code, or File System Access API calls.
- MUSKU CANNOT send or read WhatsApp messages or control desktop media keys.
- MUSKU CANNOT alter Windows system volume or shutdown/restart the computer.

If a user requests a PC control command (*"Chrome kholo"*, *"WhatsApp pe message bhejo"*, *"Volume badhao"*, *"Computer shutdown karo"*), Musku returns a polite conversational response:
> *"Main aapka computer directly control nahi kar sakti, Boss. Main aapse baat karne, aapke sawaalon ke jawab dene aur baaten yaad rakhne ke liye yahan hoon."*

---

## 2. PRODUCTION NETWORK & DEPLOYMENT ARCHITECTURE

```
                           GITHUB REPOSITORY
                                   │
                 ┌─────────────────┴─────────────────┐
                 ▼                                   ▼
          Firebase Hosting                        Render
           WEB FRONTEND                        PYTHON BACKEND
          (Static Assets)                       (app.py WS/HTTP)
                 │                                   │
                 │                                   │
                 │                              Python MUSKU
                 │                                   │
                 │                      ┌────────────┼────────────┐
                 │                      ▼            ▼            ▼
                 │                   Gemini       Firestore     Persona
                 │                    Live          Memory       Engine
                 │                      │            │            │
                 └─────────────── Firebase Auth ─────┴────────────┘
```

### Endpoints & Secret Security Reference
| Endpoint / Component | Type / Protocol | Security & Deployment Rule |
| :--- | :--- | :--- |
| **Firebase Hosting** | HTTPS (`https://<app>.web.app`) | Serves static Web UI (`index.html`, `auth.js`, stylesheets, avatars, IndexedDB cache) |
| **Render Web Service** | HTTPS / WSS (`https://<render-url>`) | Runs Python backend (`app.py`, REST endpoints `/api/chat`, `/api/start`) |
| **Render WebSocket** | WSS (`wss://<render-url>/live`) | High-speed 24kHz **`Aoede`** AI female voice bidirectional WebSocket |
| **Firebase Auth** | Identity Token | Authenticates users; backend verifies token & extracts verified `uid` |
| **Cloud Firestore** | NoSQL Database | Primary Source of Truth for per-`uid` personal memory, profile & chat history |
| **`GEMINI_API_KEY`** | Render Environment Secret | **STRICT SERVER SECRET**: Injected via Render env vars (`os.getenv`). NEVER exposed to client. |
| **`render.yaml`** | Render Blueprint | Render service definition file deploying Python backend from GitHub |

> [!NOTE]
> **Render Free Tier Note**: Render web services on the free tier sleep after periods of inactivity and re-awaken on incoming requests. This provides a 100% ₹0/no-card cost structure ideal for personal and small-scale deployment.

---

## 3. EXHAUSTIVE DIRECTORY & FILE MAP

```
musku-2.0/
├── app.py                      # 🚀 HTTP REST Server & Realtime Live Voice WS Entrypoint
├── brain_core.py               # 🧠 Primary MuskuBrain Engine, LLM Chat & Conversational Refusal Guard
├── auth_verify.py              # 🔐 Public-Key Firebase ID Token Signature Verification
├── personal_profile.py         # 🪪 Persona Facade & Time-Based Greeting Pools
├── user_context.py             # 👥 Multi-tenant Manager (Per-user Data Paths & Configurations)
├── tenant_ctx.py               # 🧵 ContextVar context manager holding active request user ID
├── language_policy.py          # 🌐 Language Normalizer (Hinglish / Hindi / English) & Prompt Locks
├── config.json                 # ⚙️ Non-secret configuration defaults (voice selection, gain, language)
├── Dockerfile                  # 📦 Docker container definition for Cloud Run deployment
├── firebase.json               # 🔥 Firebase Hosting configuration & Cloud Run rewrites
├── requirements-server.txt     # 📦 Minimal server production dependencies
├── MUSKU_WEB_ARCHITECTURE.md   # 📖 This Master Architecture Reference Manual
│
├── firebase/                   # 🔥 FIREBASE AUTH & CLOUD FIRESTORE INTEGRATION
│   ├── __init__.py             #   Package exports
│   ├── auth.py                 #   Firebase Admin Auth token verification & UID extraction
│   └── firestore.py            #   Cloud Firestore user data hierarchy persistence
│
├── persona/                    # 🎭 5-AUTHORITY PERSONA ENGINE (Immutable Identity & Adaptability)
│   ├── __init__.py             #   Public API exports for persona composition
│   ├── identity_policy.py      #   IMMUTABLE LOCK: Name="Musku", Female identity, Creator="S2 Sir"
│   ├── core_personality.py     #   Baseline traits: Intelligent, warm, confident, proactive
│   ├── relationship_engine.py  #   5 Modes: best_friend, jigri, beti, caring, girlfriend
│   ├── address_system.py       #   Dynamic Titles: Boss, Sir, Bestie, Bro, Jaan, Mamu
│   ├── tone_engine.py          #   Situational Tones: Focused, supportive, celebratory, empathetic
│   ├── persona_composer.py     #   Deterministic System Prompt Builder (Single Source of Truth)
│   ├── persona_cache.py        #   SHA-256 caching for built system prompts
│   ├── persona_versioning.py   #   Hash & version tracking metadata
│   ├── drift_guard.py          #   Guard against prompt-injection identity drift
│   └── name_resolver.py        #   User real-name extraction & persistence ("mujhe X bulao")
│
├── brain/                      # 🧩 BRAIN SUB-PACKAGE (LLM & Conversational Intent Routers)
│   ├── __init__.py             #   Package exports for brain components
│   ├── llm.py                  #   Gemini client with rate-limit RPM throttle (acquire_gemini_slot)
│   ├── memory_bridge.py        #   save_chat_log, auto_extract_and_learn, background consolidation
│   ├── conversation.py         #   In-memory conversation state & active topics
│   ├── emotion.py              #   detect_emotion, mood tracking & emotional state save
│   ├── router.py               #   Pure Conversational Intent Router (classify_conversational_intent)
│   ├── search.py               #   Google CSE web search & follow-up query solver
│   └── response.py             #   finalize_reply: Female grammar fixes, devanagari/hinglish fixes
│
├── memory/                     # 💾 LOCAL-FIRST & FIRESTORE MEMORY ENGINE
│   ├── __init__.py             #   Package exports for memory store
│   ├── paths.py                #   Single source of truth for file paths (uid-aware isolation)
│   ├── store.py                #   Categorical long-term memory (relations, preferences, tasks, reminders)
│   ├── chat.py                 #   Per-date JSON chat logs (musku_chat/<date>.json)
│   ├── context_builder.py      #   Constructs memory context blocks for LLM system prompts
│   ├── last_question.py        #   Follow-up solver ("ha batao / aage batao" continuation)
│   ├── turn_context.py         #   Learning streak and turn evaluation context
│   └── consolidate.py          #   Periodic consolidation of conversation turns into long-term facts
│
├── live/                       # 🎙️ REALTIME GEMINI LIVE VOICE & SAFE CONVERSATIONAL TOOLS
│   ├── __init__.py             #   Package init
│   ├── browser_live_ws.py      #   WebSocket server handler on /live
│   ├── musku_live_session.py   #   Per-client Gemini Live session manager (PCM input/output, tools, transcripts)
│   ├── voice_config.py         #   Voice parameters, models (gemini-3.1-flash-live-preview), Aoede voice
│   ├── live_tools.py           #   FunctionDeclarations & safe routes (saveMemory, searchWebInfo)
│   ├── search_policy.py        #   Policy for explicit web search vs knowledge answers
│   ├── search_hook.py          #   Instant search injection hook
│   ├── instant_search.py       #   Google instant search helper (returns information, no OS execution)
│   ├── barge_in.py             #   Barge-in detection when user interrupts Musku speaking
│   ├── browser_mic_bridge.py   #   Browser mic PCM 16kHz forwarder + adaptive auto-gain
│   ├── browser_audio_bridge.py #   Browser speaker bridge stub
│   ├── display_filter.py       #   live_display_text: Normalizes Musku display text for UI
│   ├── mic_meter.py            #   PCM RMS calculator for UI neural meter gauge
│   ├── voice_router.py         #   Voice routing state switch
│   └── streak_praise.py        #   Generates praise on user learning streaks
│
├── js/                         # 🌐 FRONTEND INDEXEDDB CLIENT OFFLINE CACHE
│   ├── storage/
│   │   ├── db.js               #   IndexedDB MUSKU_DB (conversations, messages, memory, profile)
│   │   ├── queue.js            #   Priority write queue (P0..P3) executed on requestIdleCallback
│   │   └── backup.js           #   Versioned backup export/import (MUSKU_BACKUP v1)
│   └── tests/                  #   Browser storage test runner & test suites
│
├── img/                        # 🖼️ Avatars & Talking-Face GIFs (Normal, Hello, Talking1-3)
├── tests/                      # 🐍 Python unit test suite (`test_persona_engine.py`, etc.)
└── index.html                  # 🎨 3D Web Dashboard UI
```

---

## 4. 5-AUTHORITY PERSONA ENGINE

Musku's identity is constructed by the `persona/` engine using 5 distinct authorities:

1. **Identity Policy (`identity_policy.py`) [IMMUTABLE]**:
   - **Name**: Musku (Female AI Assistant).
   - **Creator**: Designed by **S2 Sir**.
   - **Grammar Lock**: Female self-speech forms (`karti hoon`, `gayi`, `samajh gayi`, `bolti hoon`, `sun rahi hoon`).
2. **Core Personality (`core_personality.py`)**:
   - Intelligent, warm, witty, confident, highly capable, proactive.
3. **Relationship Engine (`relationship_engine.py`)**:
   - **Best Friend** (Default), **Jigri Dost**, **Beti**, **Caring Companion**, **Girlfriend**.
4. **Address System (`address_system.py`)**:
   - Dynamic user titles: **Boss** (Default), **Sir**, **Bestie**, **Bro**, **Jaan**, **Mamu**, or user's real name.
5. **Tone Engine (`tone_engine.py`)**:
   - Runtime adaptation to user mood (focused, stressed, celebratory, serious, empathetic).

---

## 5. MULTI-USER IDENTITY & CLOUD FIRESTORE STORAGE ENGINE

### Authenticated Identity (`firebase/auth.py`)
- User token verified via `firebase_admin.auth.verify_id_token`.
- Authoritative `uid` extracted from token and set in `tenant_ctx.set_uid(uid)`.

### Cloud Firestore Hierarchy (`firebase/firestore.py`) — PRIMARY SOURCE OF TRUTH
- `users/{uid}/profile/main`: User profile, title, relationship mode, language.
- `users/{uid}/preferences/main`: Likes, dislikes, habits, tech stack.
- `users/{uid}/memory/main`: Relations, tasks, long-term facts.
- `users/{uid}/reminders/{id}`: Scheduled alarms & due-time reminders.
- `users/{uid}/conversations/{date}`: Session metadata.
- `users/{uid}/messages/{id}`: Chat transcript messages.

> [!NOTE]
> **Persistence Hierarchy**: Cloud Firestore is the **Authoritative Source of Truth** for all user memories, profile, and chat logs across devices. IndexedDB (`MUSKU_DB`) acts purely as an **Optional Local Client Cache** for offline performance. Local server JSON files are kept only for local development fallbacks.

### Strict Multi-Tenant Security Rules (`firestore.rules`)
```protobuf
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId}/{document=**} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```
- **Cross-Tenant Guard**: User A (`UID_A`) can NEVER read or write User B's (`UID_B`) data.
- **Device Sync**: Logging in from any new device (mobile/desktop) with the same Firebase credentials automatically rehydrates the user's personal Musku profile, memories, and chat history.

---

## 6. REALTIME GEMINI LIVE VOICE & AUDIO ENGINE

- **Microphone Streaming**: Browser captures 16kHz 16-bit mono PCM via Web Audio API worklet.
- **WebSocket Gateway**: High-speed bidirectional stream to Cloud Run `/live` WebSocket.
- **Gemini Live Engine**: Gemini model `gemini-3.1-flash-live-preview` streams native 24kHz **`Aoede`** AI female voice.
- **Web Audio Resampler**: Resamples 24kHz PCM to hardware clock (44.1kHz / 48kHz) dynamically with zero playback drops.
- **Barge-in Interruption**: Realtime speech detection in `barge_in.py`; instantly mutes playback when user interrupts Musku speaking.

---

## 7. PURE CONVERSATIONAL INTENT ROUTER & SAFE TOOLS

### Conversational Intent Router (`brain/router.py`)
Classifies user text into purely conversational intents:
- `greeting`: Hello / Good morning / Namaste
- `question`: Inquiry / direct questions
- `explanation`: Requests for details or help
- `follow_up`: Continuation prompts (*"haan aage batao"*)
- `memory_query`: Queries about saved user facts or profile
- `emotional_chat`: Mood, feelings, companion banter
- `web_search`: Knowledge search queries
- `conversation`: General dialogue

### Safe Function Declarations (`live/live_tools.py`)
- `saveMemory`: Persists long-term user facts and preferences to Cloud Firestore.
- `searchWebInfo`: Performs safe Google web search to retrieve information summaries.

---

## 8. TESTING & VERIFICATION SUITE

### Python Unit Test Suite
```bash
python -m unittest discover -s tests
```
- **Status**: **PASSED** (35/35 tests passed in 0.157s).

### Frontend Storage Test Suite
```bash
node js/tests/runner.js
```
- **Status**: **PASSED** (13/13 tests passed).


