# 🧠 MUSKU 2.0 — WEB CONVERSATIONAL AI : WORKING FLOW & STRUCTURE MANUAL

> **Workspace:** `D:\4\musku-2.0` | **Mode:** Browser-First Inline Live (`BROWSER_MIC_ENABLED=True`, `BROWSER_LIVE_WS=True`, `MUSKU_INLINE_LIVE=True`) | **Model:** `gemini-3.1-flash-live-preview` voice `Aoede` | **Generated:** 2026-08-29 scan (actual source code)

---

## 1. WHAT MUSKU IS (PRODUCT BOUNDARY)

MUSKU 2.0 is a pure **Web Conversational AI Female Assistant** — realtime voice + text chat.

*   **Realtime voice** — Gemini Live native `AUDIO` 24kHz `Aoede` female voice (no local TTS).
*   **Text chat** — `POST /api/chat` via `brain_core.py` + Gemini fallback.
*   **Auth:** Firebase ID token (`firebase/auth.py` verify), per-uid Firestore isolation.

**Security boundary:** `ZERO` computer/desktop/OS control. Any PC-control tool request → polite refusal `musku_live_session.py:_execute_tool` + `persona/identity_policy.py` feminine speech lock.

---

## 2. COMPLETE WORKING FLOW (END-TO-END)

```
┌─────────────────────────── BROWSER (index.html + js/) ───────────────────────────┐
│  Mic (getUserMedia 16k) ─▶ AudioContext 16k ─▶ resampleFloatTo16k ─▶ WS /live     │
│  Speaker ◀── 24kHz PCM base64 ◀── WS /live   (muskuPlayPcm 24000Hz)               │
│  Chat:  TYPE COMMAND #txtCmd ─▶ POST /api/chat ─▶ reply bubble                   │
│  IndexedDB MUSKU_DB (local cache)                                                │
└───────────────┬───────────────────────────────┬──────────────────────────────────┘
                │ ws://host:8770/live            │ HTTPS GET static + POST /api/*
                ▼                               ▼
┌─────────────────────────── PYTHON BACKEND (app.py) ──────────────────────────────┐
│  app.py:MuskuHTTPRequestHandler  /api/start, /api/chat, WSGI handler()           │
│  live/browser_live_ws.py         1 session per verified uid (port 8770)          │
│  live/musku_live_session.py      Gemini Live bridge (google-genai SDK)            │
│  brain_core.py / brain/*         text chat + memory + persona                    │
│  user_context.py / tenant_ctx.py per-uid config + ContextVar                     │
│  firebase/*                      Auth verify + Firestore primary truth           │
└───────┬───────────────────────────┬───────────────────────────┬──────────────────┘
        ▼                           ▼                           ▼
   Gemini Live API            Cloud Firestore              Local JSON fallback
   (voice Aoede)              (users/{uid}/...)            (musku_chat / musku_data)
```

### 2.1 Boot (`app.py:main`)
1. `browser_live_ws.start()` → `/live` WS on `0.0.0.0:8770` (`live/voice_config.py:109`).
2. `start_http_server()` → `index.html`, `ui_theme.css`, `img/` on `:8000` (`app.py:216`).
3. `load_config()` crash-proof (`app.py:58`) — `00` corrupt → `[WARN]` + defaults + `.corrupt.bak`.
4. Vercel WSGI `handler()` same `/api/chat` logic.

---

## 3. GRID — `Greed/Grid` Actually is CSS Grid (No Business Logic)

No `muku_greed` logic — term is **MUSKU + CSS Grid**.

**Root:** `index.html:126`
```css
.app { display:grid; grid-template-columns:1fr 2fr 1fr; grid-template-rows:minmax(0,1fr); gap:10px; height:100vh; padding:14px; }
.app > aside.panel LEFT | main.center.panel CENTER 2fr | aside.panel RIGHT
```

**DOM** `index.html:2079` `.app` → LEFT (gauges SYSTEM SOUND APPS #appList) → CENTER (title .stage 450px gif .eq 16 bars #startBtn) → RIGHT (avatar popover TYPE COMMAND #txtCmd LIVE CHAT #chatFeed)

**Sub-grids:** `index.html:184` `.gauges {grid-template-columns:repeat(4,minmax(0,1fr))}` → SOUND/MIC/BRAIN/LEVEL gauges. `.panel, .sec.fill` flex.

---

## 4. START BUTTON — CLICK CHAIN (FULL)

### 4.1 HTML + JS `index.html`
*   Button `index.html:3080` `<button id="startBtn" class="btn">START</button>` `.btn.stop` green.
*   Helpers `index.html:3153` `syncStartButton(active)` text `START↔STOP`, `setMicListeningState(on)` flag + `_muskuClearMicSendBuf`.
*   **Browser path `index.html:7601 startAll()` (current, 4 fixes applied):**
    1. `if(active) return` + `getKey()` check → `openApiKeyDirect()` if missing.
    2. `setVoiceActive(true)` + `muskuResumeAudio()` (24kHz AudioContext resume).
    3. `greet = greetingText()` (`:7587` time `Good morning/afternoon/evening/night dear`).
    4. `setStatus("speaking")` + `ensureMuskuPending()` bubble + `muskuMicListening=true`.
    5. **Mic separate:** `if(!muskuMicGranted && muskuRequestMic) muskuRequestMic().catch(()=>{})` fire-and-forget — **greeting not blocked**.
    6. **HTTP backup queue:** `fetch("/api/start",{uid,greet,token, Authorization:Bearer})` → `app.py:116` queue.
    7. **WS primary:** `connectLiveWs().then(()=> window.muskuLiveWs.send(JSON.stringify({text:"[INTERNAL - START GREETING: "+greet+"]"})))` (`:7728`). If WS fail, HTTP queue covers — no local TTS (authoritative Gemini).

*   `stopAll()` `index.html:7644` → `active=false`, `muskuStopAudio()`, `speechSynthesis.cancel()`, `muskuLiveWs.close(1000)`, clear buffers, `syncStartButton(false)` `stopped`.
*   Desktop header `index.html:5240` `#startBtn` pywebview handler — same mic-separate fix (no early `return`), else `pywebview.api.toggle()`.

### 4.2 Python `/api/start` `app.py:115`
```py
body = json.loads(rfile.read(...))
token = extract_token(headers, body); uid = resolve_verified_uid(token, body.uid)
if uid is None: 401
script = body.get("greet") or body.get("script")
browser_live_ws.send_start_greeting(uid, script=script)  # line 138 force+queue
return {"status":"ok"}
```

### 4.3 WS Server `live/browser_live_ws.py`
*   `__init__:77` `_pending_greetings: dict uid->script|True` (script-preserving).
*   `send_start_greeting(uid, script)` `160` — if `sess.active` → `sess.send_greeting(script, force=True)` direct, else `pending[uid]=script`.
*   `_handler:285` extract `token/key/uid` query, `verify_firebase_token` → `vuid`, `resolve_verified_uid` 401.
*   `_handler_inline_live:322` `set_uid(vuid)`, `load_config(vuid)`, one-session-per-uid `_sessions[ukey]`, `get_live_system_prompt(user_name, language, rel_mode, uid)` (`voice_config.py:304`), `MuskuLiveSession(ws, api_key, prompt, uid)`, flush: `pending = pop(ukey)` → `session._greet_on_connect=True; if str: session._pending_greeting=pending` `388`, then `session.run()`.

---

## 5. 🔔 GREETING MESSAGE — HOW IT ARRIVES (DETAILED, LATEST 4 FIXES)

### 5.1 Diagram (GREETING ONLY)

```
START tap (index.html:7601)
  ↓ getKey() ok → greet = greetingText() "Good morning dear"
  ↓ setStatus speaking + ensureMuskuPending() + muskuResumeAudio() 24kHz
  ↓ fork 1: fetch POST /api/start {uid,greet,token} ──┐
  ↓ fork 2: connectLiveWs() -> WS OPEN ──┐             │
                                         │             ▼
                            live/browser_live_ws.py:160 send_start_greeting(uid, script)
                                         │             ├─ if session.active → send_greeting(script, force=True)
                                         │             └─ else pending[uid]=script (queue)
                                         ▼
Live WS Connected? YES → Gemini Live Session Ready? (musku_live_session.py:204)
  ↓ YES                    ↓ NO (connecting_gemini)
  ↓                        └─ queued → run():214 flush await send_greeting(pending, force=True)
  ↓ YES → Fresh Greeting (force=True har tap, no dedupe block)
  ↓ personal_profile.py:79 build_start_greeting_prompt(script)
  │   base = script or get_respectful_start_greeting() 66 ("Good morning {dear/name}")
  │   para = random 5 ("Aaj ka din pyaara ho dear!...", "Arey dear, awaz sunkar...")
  │   => "Good morning dear. Aaj ka din pyaara ho dear! Batao aaj kya karna hai..."
  ↓ live/musku_live_session.py:261 send_greeting(script, force=True)
  │   if _greeted and not force: return (else force passes)
  │   await send_proactive_prompt(prompt) 249 -> sess.send_realtime_input(text=prompt)
  ↓ Gemini Live (gemini-3.1-flash-live-preview, voice Aoede, live/voice_config.py:22,381)
  ↓ 24kHz PCM Audio (OUTPUT_SAMPLE_RATE 24000)
  ↓ musku_live_session.py:411 _on_gemini inline_data -> b64 -> ws.send({"type":"audio", audio:b64}) 448
  ↓ index.html:6744 onmessage audio -> muskuPlayPcm(b64) 6379 OUT_RATE 24000 -> AudioBuffer -> speaker
  ↓ 🔊 Greeting Voice (real Aoede, no local TTS)
```

### 5.2 Files:Line for Greeting

| Function | File:Line | Note |
|---|---|---|
| `greetingText()` | `index.html:7587` | time-based |
| `build_start_greeting_prompt` | `personal_profile.py:79` | script + random para |
| `send_greeting(force)` | `live/musku_live_session.py:261` | `force=True` fresh, queue if no session |
| `send_start_greeting` | `live/browser_live_ws.py:160` | script-preserving |
| `run()` flush | `live/musku_live_session.py:214` | `force=True` + clear |
| `_on_browser` START GREETING | `live/musku_live_session.py:348` | `force=True` |
| `app.py /api/start` | `app.py:115` | preserves `greet` |
| `muskuPlayPcm` | `index.html:6379` | `OUT_RATE 24000` |
| `_pending_greetings` | `live/browser_live_ws.py:77` | `uid->script` |

### 5.3 4 Mandatory Fixes (Current, Applied 2026-08-29)

1. **Har START → 1 fresh** `force=True` + reset `finally: _greeted=False` `musku_live_session.py:243`.
2. **Gemini not ready → queue → auto send** `browser_live_ws.py:170` + `musku_live_session.py:214` + `index.html:7728` dual WS+HTTP.
3. **Mic not blocking** `index.html:7601,5240` fire-and-forget, greeting `speaking` while mic `listening` later.
4. **Existing pipeline same** `24kHz PCM WS muskuPlayPcm` no TTS, no grid/chat change.

**Constraints honored:** Grid `1fr 2fr 1fr` no, chat `#chatFeed` no, mic mix no, local TTS no.

---

## 6. 🎙️ LIVE VOICE GENERATION (Shared with Greeting, Also for Voice-to-Voice)

*Not greeting-only — same pipeline for ongoing voice chat.*

**Config** `live/voice_config.py:22` `DEFAULT_MODEL gemini-3.1-flash-live-preview`, `27 INPUT 16000 mono`, `33 OUTPUT 24000`, `71 FRAME 1280 (40ms)`, `68 INSTANT_VOICE 1`, `109 WS 0.0.0.0:8770`, `381 VOICE Aoede` (config.json `musku_voice` > env).

**Connect** `musku_live_session.py:66 build_musku_connect_config(system_prompt, language)` → `SpeechConfig(Aoede)` + `LiveConnectConfig(response_modalities=[AUDIO], system_instruction, tools, input/output transcription hi-IN)` → `client.aio.live.connect(model, config)` `202`, `status: connecting_gemini/connected/gemini_ready` `204`.

**Loop:**
*   Mic `index.html:6662` `getUserMedia echoCancellation` → `AudioContext 16000` → `resampleFloatTo16k 48k→16k` `6666` → `floatTo16` → `appendMicPcm` → `WS {audio:b64}` + `pywebview.api.on_browser_mic_chunk` meter `4642`.
*   Server `musku_live_session.py:326` `_apply_mic_gain` + `Blob(mime="audio/pcm;rate=16000")` → `send_realtime_input(audio)`.
*   Gemini `_on_gemini:411` `inline_data PCM b64` → `{audio}` → browser `AudioContext 24kHz` play (`muskuPlayPcm`), `output_transcription` bubble, `turnComplete` → `persist_and_sync`.

**Tools:** `live_tools.py` `saveMemory` → `memory/store.py`, `searchWebInfo` → `brain/search.py`, PC-control → refusal. Sequential `send_tool_response`.

**Persona live updates:** `update_system_prompt` `283` realtime inject, `detect_persona_mode` `369` relationship switch.

**Voice-to-Voice vs Greeting isolation:** Greeting branch early `return` `348` before normal `audio 320` / `text 360` handling → ongoing voice unaffected.

---

## 7. 💬 TEXT CHAT FLOW (Separate from Live Voice)

`index.html` `#txtCmd` → `app.py:143 POST /api/chat` `{text, uid, key}` → `resolve_verified_uid` 401 → `user_context.set_uid/load_config` per-uid → `MuskuBrain(user_name).get_response(text)` (`brain_core.py`) → if `Desktop control not active` fallback `_gemini_chat([{role:"system", prompt boss_instruction},{role:"user",text}], api_key)` → `{"reply": reply}` → browser `chatFeed` bubble. Also Vercel WSGI `handler:262` same. `rate_ok` 30/min `app.py:43`. Chat does **not** go through Live WS.

---

## 8. 💾 CHAT STORAGE (3-LAYER)

**Layer1 Firestore PRIMARY** `firebase/firestore.py` `users/{uid}/profile, preferences, memory/{category}, reminders/{id}, conversations/{date}/turns/{auto}` `save_chat_turn_fs`. `firestore.rules` `request.auth.uid==userId`.

**Layer2 Local JSON** `memory/chat.py:save_chat` → Firestore + `musku_chat/<date>.json` ring + `recent_turns.json` + `chat_summary.txt`. `memory/store.py` categorical.

**Layer3 IndexedDB** `js/storage/db.js` `MUSKU_DB` stores `conversations, messages, memory, user_profile, persona_state`. `queue.js` P0-3, `backup.js` export.

**Save trigger:** text `memory_bridge.py:110 save_chat_log` → `chat.save_chat`; voice `turn_complete` → `_persist_and_sync` `musku_live_session.py:596` → same `save_chat_log` → `{memory_sync}` to UI. `voice_config.get_live_memory_block:230` builds prompt memory (turn_context + store + recent 10 + summary + last_question PREVIOUS-REPLY RULE).

---

## 9. MULTI-TENANT ISOLATION

`auth_verify.py` `extract_token/resolve_verified_uid`, `tenant_ctx.py` ContextVar `uid`, `user_context.py` per-uid `load_config/set_uid/ensure_user_dir`, `memory/paths.py` uid-aware paths. `to_thread` re-establish `set_uid(uid)` in `_persist_turn_and_consolidate:606`.

Runtime per-uid: `turn_context.py`, `conversation.py`, `emotion.py`, `store.py`, `chat.py`, `browser_live_ws/musku_live_session` per-uid session.

---

## 10. DIRECTORY MAP (ACTUAL 2026-08-29)

```
musku-2.0/
├── app.py                 # HTTP :8000 + /live :8770 + /api/chat, /api/start + crash-proof load_config
├── index.html             # 3-col grid + #startBtn + muskuPlayPcm 24k + startAll dual greeting
├── personal_profile.py    # get_respectful_start_greeting 66, build_start_greeting_prompt 79
├── user_context.py        # per-uid config (atomic _write_json) + persona switch
├── tenant_ctx.py, auth_verify.py, language_policy.py, crypto_utils.py
├── config.json            # musku_voice Aoede, gain 2.4, language hinglish (encrypted key)
├── firebase/auth.py, firestore.py, firestore.rules
├── persona/               # identity, core_personality, relationship, address, tone, composer...
├── brain/ llm.py, memory_bridge.py, conversation.py, emotion.py, router.py, search.py, response.py
├── brain_core.py          # MuskuBrain + _gemini_chat fallback
├── memory/ paths.py, store.py, chat.py, turn_context.py, last_question.py, consolidate.py, context_builder.py
├── live/ browser_live_ws.py (force+queue 160), musku_live_session.py (force 261, flush 214), voice_config.py (single source), live_tools.py, mic_meter.py, display_filter.py, browser_mic/audio_bridge.py
├── js/storage/ db.js, queue.js, backup.js, historyService.js + tests/
├── img/1..6/, musku_chat/, musku_data/, musku_users/{uid}/
├── tests/ + MUSKU_WEB_ARCHITECTURE.md (this file)
```

---

## 11. CONFIG KNOBS (`live/voice_config.py` + `config.json`)

| Key | Default | Meaning |
|---|---|---|
| `GEMINI_LIVE_MODEL` | `gemini-3.1-flash-live-preview` | Live model |
| `GEMINI_LIVE_VOICE` / `musku_voice` | `Aoede` | Female voice (VOICES: Kore,Leda,Orus,Zephyr,Puck,Charon,Fenrir,Aoede) |
| `BROWSER_LIVE_WS_PORT` | `8770` | /live WS port |
| `INPUT_SAMPLE_RATE` | `16000` | Mic → Gemini |
| `OUTPUT_SAMPLE_RATE` | `24000` | Gemini → speaker |
| `FRAME_BYTES` | `1280` | 40ms @16k |
| `INSTANT_VOICE_MODE` | `1` | low latency buffers |
| `JS_MIC_GAIN` / `MIC_INPUT_GAIN` | `3.0 / 1.0` | mic boost |
| `musku_voice_gain` | `2.4` | speaker gain |
| `MUSKU_LIVE_TOOLS` | `1` | saveMemory/search |
| `USER_IDLE_CHECKIN_SECS` | `60` | proactive check-in |

---

## 12. HOW TO RUN

```bash
cd musku-2.0
pip install -r requirements-server.txt
python app.py            # http://localhost:8000 + ws://localhost:8770/live
```
Text-only Vercel via `app.py:handler`. `config.json` crash-proof + atomic write.

---

## 13. TESTING

```bash
python -m unittest discover -s tests
node js/tests/runner.js
python -c "import live.voice_config as c; assert c.OUTPUT_SAMPLE_RATE==24000; assert c.INPUT_SAMPLE_RATE==16000"
python -c "from live.musku_live_session import MuskuLiveSession; assert 'force' in MuskuLiveSession.send_greeting.__code__.co_varnames"
```
Greeting manual: `START` → WS `{"text":"[INTERNAL - START GREETING: Good morning dear]"}` → log `Gemini connected` → WS `{"type":"audio"}` → Aoede 24kHz. `STOP->START` 3x fresh para, mic denied still greeting.

