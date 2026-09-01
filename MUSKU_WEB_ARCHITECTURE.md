# 🧠 MUSKU 2.0 — WEB CONVERSATIONAL AI : FULL WORKING PROCESS MANUAL

> **Workspace:** `D:\4\musku-2.0` | **Mode:** Browser-First Inline Live (`BROWSER_MIC_ENABLED=True`, `BROWSER_LIVE_WS=True`, `MUSKU_INLINE_LIVE=True`) | **Model Live:** `gemini-3.1-flash-live-preview` voice `Aoede` | **Model Text:** `gemini-3.5-flash-lite` (backup `gemini-3.5-flash`) | **Generated:** 2026-09-01 scan (actual source code — 100% verified)

---

## 1. WHAT MUSKU IS — PRODUCT BOUNDARY

MUSKU 2.0 is a **pure Web Conversational AI Female Assistant** — realtime voice + text chat. **No desktop/OS control.**

| Capability | How | File |
|---|---|---|
| **Realtime voice** | Gemini Live native `AUDIO` 24kHz `Aoede` female voice — no local TTS | `live/musku_live_session.py:83`, `live/voice_config.py:388` |
| **Text chat** | `POST /api/chat` via `MuskuBrain` + Gemini fallback | `app.py:212`, `brain_core.py:1052` |
| **Auth** | Firebase ID token RS256 verify (`auth_verify.py`), per-uid Firestore isolation | `auth_verify.py:94`, `firebase/auth.py` |
| **Memory** | 3-layer (Firestore + Local JSON + IndexedDB) | `memory/`, `firebase/firestore.py` |

**Security boundary:** Any PC-control / image-generation / code-execution request → polite upgrade refusal `brain_core.py:12 execute_system_command` + `live/musku_live_session.py:847 _execute_tool` + `persona/identity_policy.py` feminine speech lock. Live tools are **only** `saveMemory` + `searchWebInfo` (`live/live_tools.py:22`).

---

## 2. HIGH-LEVEL ARCHITECTURE (END-TO-END)

```
┌──────────────────────────── BROWSER (index.html 8412 lines + js/ + auth.js 1069) ────────────────────────────┐
│  Mic getUserMedia 16k ─▶ AudioContext 16k ─▶ resampleFloatTo16k ─▶ WS /live  (binary PCM base64)             │
│  Speaker ◀── 24kHz PCM base64 ◀── WS /live  (muskuPlayPcm 24000Hz AudioBuffer)                               │
│  Chat: TYPE COMMAND #txtCmd ─▶ POST /api/chat ─▶ reply bubble #chatFeed                                      │
│  Auth: Firebase Google Sign-In → idToken (refresh 50m) → Authorization: Bearer on every request             │
│  IndexedDB MUSKU_DB v1 (7 stores) + queue.js P0-3 + backup.js                                                │
└────────────────┬──────────────────────────────┬──────────────────────────────────────────────────────────────┘
                 │ ws://host:8770/live           │ HTTPS GET static + POST /api/*
                 │ (or wss://host:$PORT/live    │
                 │  single-port PaaS)            │
                 ▼                               ▼
┌──────────────────────────────── PYTHON BACKEND (app.py 690) ────────────────────────────────────────────────┐
│  MuskuHTTPRequestHandler  GET /, /health, /index.html, /js/*, /img/* + POST /api/start, /api/chat,          │
│                          /api/save-key + WSGI handler() for Vercel + single-port HTTP bridge               │
│  live/browser_live_ws.py (595)  1 session per verified uid on port 8770 (or $PORT)                          │
│  live/musku_live_session.py (889) Gemini Live bridge (google-genai SDK) — thin, per-client                  │
│  live/voice_config.py (421) SINGLE SOURCE for all knobs + prompt builder                                    │
│  brain_core.py (2709) + brain/* text brain delegation + transliteration dictionary 5000+ words               │
│  memory/* + persona/* + user_context.py (342) per-uid isolation via tenant_ctx.py ContextVar                │
│  firebase/* Auth verify + Firestore primary truth + crypto_utils.py Fernet BYOK                              │
└──────────┬──────────────────────────┬────────────────────────────┬──────────────────────────────────────────┘
           ▼                          ▼                            ▼
      Gemini Live API           Cloud Firestore               Local JSON fallback
      (voice Aoede 24k)         (users/{uid}/...)             (musku_users/{uid}/musku_data|musku_chat)
      gemini-3.1-flash-live     Realtime DB traces            IndexedDB MUSKU_DB (browser)
```

**Boot `app.py:main` (`app.py:645`)**
1. `browser_live_ws.start()` → `/live` WS on `0.0.0.0:8770` or `$PORT` if `MUSKU_LIVE_WS_PORT` not set → single-port detection `port==PORT` → `_process_http` multiplex (`browser_live_ws.py:263`)
2. `start_http_server()` → static `index.html`, `ui_theme.css`, `img/`, `js/` on `:8000` (`app.py:390`) — skipped if single-port (WS handles HTTP)
3. `load_config()` crash-proof (`app.py:90`) — null-byte/empty → `[WARN]` + defaults + `.corrupt.bak` backup, atomic `_write_json` via `tempfile+fsync+os.replace` (`user_context.py:304`)
4. Vercel WSGI `handler()` (`app.py:439`) mirrors all `do_POST`/`do_GET` logic; `app = handler` (`app.py:642`)

---

## 3. DIRECTORY MAP — ACTUAL 2026-09-01

```
musku-2.0/
├── app.py                          690  HTTP :8000 + /live :8770 + WSGI handler + CORS/rate-limit/blocklist
├── index.html                     8412  3-col grid + #startBtn + AudioContext 16k→24k + startAll dual greeting
├── auth.js                        1069  Firebase Google Sign-In + musku_traces + FREE/Pro HMAC activation
├── auth.css / ui_theme.css               13 themes (amethyst..pink) + auth UI
├── brain_core.py                  2709  Legacy monolith: get_response + _gemini_chat + deva_to_hinglish + PC stub
├── brain/                                Text brain delegation
│   ├── llm.py                      122  get_gemini_client per-key cache + acquire_gemini_slot 14 RPM
│   ├── router.py                    58  classify_conversational_intent, is_fast_pc_command=false
│   ├── conversation.py             275  UID-scoped conversation_state.json + topic/pending_question
│   ├── memory_bridge.py            204  save_chat_log + _consolidate_background (consolidate 14 turns)
│   ├── emotion.py                  148  Emotion detection for response tailoring
│   ├── response.py                 162  Post-processing + grammar fix
│   ├── search.py                    27  web_search wrapper (Google CSE fallback)
│   └── __init__.py                  13
├── memory/                               Storage data layer (paths = single source)
│   ├── paths.py                    234  PEP562 __getattr__ UID-aware DATA_DIR/HISTORY_DIR/FILE_MAP atomic
│   ├── store.py                    447  save_memory dedup hash + Firestore dual + prune + format_live_memory_card
│   ├── chat.py                     296  save_chat ring 20 + daily 200 + recent_turns + summary 800 chars
│   ├── turn_context.py             308  record_last_user/musku + streak 2,3,5,8,13 + get_live_turn_context_block
│   ├── last_question.py            150  PREVIOUS-REPLY RULE store (ha batao → repeat)
│   ├── consolidate.py              109  LLM ADD/UPDATE/REMOVE via Gemini
│   ├── context_builder.py           23  Merge context
│   ├── service.py                   79  save_memory wrapper with confidence
│   └── __init__.py                  65
├── persona/                              Persona engine (12 files)
│   ├── persona_composer.py          50  build_persona_prompt (core+identity+relationship+tone+drift)
│   ├── relationship_engine.py      123  Alias map best_friend/jigri/beti/caring/girlfriend + custom dynamic
│   ├── core_personality.py          23  Flirty-chulbul, aap, no hehe unless joke, Musku lock
│   ├── name_resolver.py            155  resolve_greeting_term + maybe_save_user_name (mujhe X bulao)
│   ├── identity_policy.py          135  Musku name lock, MUSKU_CREATOR S2, feminine enforcement, upgrade note
│   ├── address_system.py            27  Greeting term resolver
│   ├── tone_engine.py               19
│   ├── drift_guard.py               15
│   ├── abuse_policy.py             104  is_abusive + POLITE_BOUNDARY_BLOCK (injected into all prompts)
│   ├── persona_cache.py             31
│   ├── persona_versioning.py         5
│   └── __init__.py                  23
├── personal_profile.py             118  Facade: boss_instruction, get_respectful_start_greeting, build_start_greeting_prompt (20 variants)
├── user_context.py                 342  load_config/save_config per-uid (Firestore wins→file→defaults), dual write, encrypted
├── tenant_ctx.py                    39  ContextVar musku_uid + safe_uid regex + is_owner
├── auth_verify.py                  178  RS256 x509 cache 1h + resolve_verified_uid fail-closed + extract_token
├── language_policy.py              108  normalize_language + get_language_persona_rules (hi-IN/en-IN/hinglish)
├── crypto_utils.py                  95  Fernet PBKDF2(machineId+SALT) + 10-layer re-encrypt
├── live/                                 Live voice subsystem (single source voice_config.py)
│   ├── voice_config.py             421  SINGLE SOURCE: model Aoede, 16k→24k, 40ms frame 1280, gains, VAD, queues, prompt builders
│   ├── browser_live_ws.py          595  BrowserLiveWSServer: per-uid session, pending_greetings dict, Origin check, single-port bridge
│   ├── musku_live_session.py       889  MuskuLiveSession: Gemini connect, browser_loop↔gemini_loop, tools, persist
│   ├── live_tools.py                78  ONLY saveMemory + searchWebInfo declarations
│   ├── display_filter.py            71  live_display_text + filter_unnecessary_laughter
│   ├── mic_meter.py                 20  publish_pcm_meter
│   ├── barge_in.py                  73  BargeInDetector + NoOp
│   ├── browser_mic_bridge.py       267  Legacy mic bridge (not used in inline)
│   ├── browser_audio_bridge.py      77  Legacy audio bridge
│   ├── voice_router.py             130  VoiceRouter (VOICE_ROUTER_ENABLED=0 default)
│   ├── search_hook.py               70  Instant Google hook (INSTANT_SEARCH_HOOK=0)
│   ├── search_policy.py            102
│   ├── instant_search.py           350  Parallel search narration (disabled)
│   ├── telemetry.py                 37  TurnTelemetry
│   └── streak_praise.py             51  Correct streak celebration 2,3,5,8,13
├── realtime/                             Legacy desktop lane — NOT in inline web path but present
│   ├── event_bus.py                 43  Pub/sub AI_AUDIO_CHUNK, USER_SPEECH_PARTIAL/FINAL, TURN_COMPLETE
│   ├── state_machine.py             45  SystemState enum
│   ├── orchestrator.py             211  Wires voice_router + session_controller
│   ├── voice_supervisor.py         208
│   ├── turn_manager.py              42
│   ├── gate_controller.py           57
│   └── session_controller.py        45
├── firebase/
│   ├── auth.py                      87  verify_firebase_token via firebase_admin fallback
│   ├── firestore.py                139  save_user_profile/chat_turn/categorical_memory (users/{uid}/...)
│   ├── api_keys.py                  72  BYOK load/save per-uid (Gemini key cross-device)
│   └── __init__.py                   1
├── js/storage/
│   ├── db.js                       146  IndexedDB MUSKU_DB v1 — 7 stores (conversations/messages/memory/user_profile/persona_state/projects/metadata)
│   ├── queue.js                     60  P0-3 priority queue for offline
│   ├── backup.js                    98  Export/restore JSON
│   └── historyService.js            79  Daily fetch + recall window
├── js/tests/  runner.js + storage-*.test.js
├── tests/  test_auth_verify, test_multitenant*, test_persona_engine, test_name_resolver, conftest
├── img/1..6/  Hello.gif, Normal.gif, Talking*.gif + jpg
├── musku_users/{uid}/  per-uid isolated config.json + musku_data/ (15 category files) + musku_chat/ (daily json)
├── musku_data/ + musku_chat/  legacy owner (uid=owner) fallback
├── config.json / config.example.json  musku_voice Aoede, gain 1.8/2.4, language hinglish, encrypted gemini key
├── requirements.txt / requirements-server.txt (7 lines)  google-genai, websockets, cryptography, firebase-admin, etc.
├── Dockerfile (24)  PORT 8000 single-port + CMD python app.py
├── vercel.json (20)  rewrites + CSP + function
├── firebase.json (32)  hosting + run.serviceId musku-web-backend us-central1
├── firestore.rules (18) + database.rules.json (72)  request.auth.uid==userId
├── DEPLOY.md (80) / README.md / AGENTS.md
└── MUSKU_WEB_ARCHITECTURE.md (this file)
```

---

## 4. GRID — CSS Grid (No Business Logic)

No `muku_greed` logic — term is **MUSKU + CSS Grid**.

**Root:** `index.html:126`
```css
.app { display:grid; grid-template-columns:1fr 2fr 1fr; grid-template-rows:minmax(0,1fr); gap:10px; height:100vh; padding:14px; }
.app > aside.panel LEFT | main.center.panel CENTER 2fr | aside.panel RIGHT
```
**DOM** `index.html:2079` `.app` → LEFT (gauges SYSTEM SOUND APPS #appList) → CENTER (title .stage 450px gif .eq 16 bars #startBtn) → RIGHT (avatar popover TYPE COMMAND #txtCmd LIVE CHAT #chatFeed)

**Sub-grids:** `index.html:184` `.gauges {grid-template-columns:repeat(4,minmax(0,1fr))}` → SOUND/MIC/BRAIN/LEVEL. `.panel, .sec.fill` flex. 13 themes in `ui_theme.css:1`.

---

## 5. START BUTTON — CLICK CHAIN (FULL)

### 5.1 HTML + JS `index.html`

* Button `index.html:3080` `<button id="startBtn" class="btn">START</button>` `.btn.stop` green.
* Helpers `index.html:3153` `syncStartButton(active)` text `START↔STOP`, `setMicListeningState(on)` flag + `_muskuClearMicSendBuf`.
* **Browser path `index.html:7601 startAll()` (current, 4 fixes applied):**
  1. `if(active) return` + `getKey()` check → `openApiKeyDirect()` if missing.
  2. `setVoiceActive(true)` + `muskuResumeAudio()` (24kHz AudioContext resume).
  3. `greet = greetingText()` (`:7587` → time `Good morning/afternoon/evening/night dear`).
  4. `setStatus("speaking")` + `ensureMuskuPending()` bubble + `muskuMicListening=true`.
  5. **Mic separate:** `if(!muskuMicGranted && muskuRequestMic) muskuRequestMic().catch(()=>{})` fire-and-forget — **greeting not blocked**.
  6. **HTTP backup queue:** `fetch("/api/start",{uid,greet,token, Authorization:Bearer})` → `app.py:116` queue.
  7. **WS primary:** `connectLiveWs().then(()=> window.muskuLiveWs.send(JSON.stringify({text:"[INTERNAL - START GREETING: "+greet+"]"})))` (`:7728`). If WS fail, HTTP queue covers — no local TTS (authoritative Gemini).

* `stopAll()` `index.html:7644` → `active=false`, `muskuStopAudio()`, `speechSynthesis.cancel()`, `muskuLiveWs.close(1000)`, clear buffers, `syncStartButton(false)` `stopped`.
* Desktop header `index.html:5240` `#startBtn` pywebview handler — same mic-separate fix.

### 5.2 Python `/api/start` `app.py:115`

```py
body = json.loads(rfile.read(...))
token = extract_token(headers, body); uid = resolve_verified_uid(token, body.uid)
if uid is None: 401
script = body.get("greet") or body.get("script")  # sanitized 80 chars, no [INTERNAL/SYSTEM/IGNORE, strip []\n
browser_live_ws.send_start_greeting(uid, script=script)  # line 138 force+queue
return {"status":"ok"}
```

### 5.3 WS Server `live/browser_live_ws.py`

* `__init__:82` `_sessions: dict uid->MuskuLiveSession`, `_pending_greetings: dict uid->script|None`, `_system_prompt_overrides: dict uid->prompt` (per-uid, not global — prevents leak).
* `send_start_greeting(uid, script)` `176` — if `sess.active` → `sess.send_greeting(script, force=True)` direct, else `pending[uid]=script`.
* `_handler:425` Origin check (`ALLOWED_ORIGIN` + `*.vercel.app|*.runxbuild.app|localhost:8000` else `1008`), verify query `token/key/uid`, `verify_firebase_token` → `vuid`, `resolve_verified_uid` 401.
* `_handler_inline_live:487` `set_uid(vuid)`, `load_config(vuid)`, ensures `ensure_user_dir`, one-session-per-uid guard (`already active` → `1008`), `get_live_system_prompt(user_name, language, rel_mode, uid)` (`voice_config.py:312`), `MuskuLiveSession(ws, api_key, prompt, uid)`, flush: `pending = pop(ukey)` → `session._greet_on_connect=True; if str: session._pending_greeting=pending` `554`, then `session.run()`.
* Single-port PaaS: `_process_http:263` builds WSGI environ from websockets `Request`, delegates to `app.handler` — `/live` → WS handshake, else → HTTP. `_async_main:343` patches `Request.parse` to allow `POST` (otherwise RunxBuild `502`).

---

## 6. 🔔 GREETING MESSAGE — HOW IT ARRIVES (DETAILED, LATEST 4 FIXES)

### 6.1 Diagram (GREETING ONLY)

```
START tap (index.html:7601)
  ↓ getKey() ok → greet = greetingText() "Good morning dear" (7587 time-based)
  ↓ setStatus speaking + ensureMuskuPending() + muskuResumeAudio() 24kHz
  ↓ fork 1: fetch POST /api/start {uid,greet,token} ──┐
  ↓ fork 2: connectLiveWs() -> WS OPEN ──┐             │
                                         │             ▼
                           live/browser_live_ws.py:176 send_start_greeting(uid, script)
                                         │             ├─ if session.active → send_greeting(script, force=True)
                                         │             └─ else pending[uid]=script (queue)
                                         ▼
Live WS Connected? YES → Gemini Live Session Ready? (musku_live_session.py:204)
  ↓ YES                    ↓ NO (connecting_gemini)
  ↓                        └─ queued → run():235 flush await send_greeting(pending, force=True)
  ↓ YES → Fresh Greeting (force=True har tap, no dedupe block)
  ↓ personal_profile.py:82 build_start_greeting_prompt(script)
  │   base = script or get_respectful_start_greeting() 67 ("Good morning {dear/name}" via name_resolver)
  │   variants = 20 distinct ("Main bhi yahin hoon...", "Aaj ka din pyaara ho...", "Heey ekdum ready...")
  │   dedupe via _LAST_GREETING random.choice(pool)
  │   => "[INTERNAL GREETING — Speak EXACTLY this warm greeting verbatim, natural Aoede voice, do not paraphrase, 1-2 sentences only: \"Good morning dear! Aaj ka din pyaara ho...!\"]"
  ↓ live/musku_live_session.py:286 send_greeting(script, force=True)
  │   if _greeted and not force: return (else force passes)
  │   if !_session: queued (_pending_greeting = script) return
  │   await send_proactive_prompt(prompt) 271 -> sess.send_realtime_input(text=prompt)
  ↓ Gemini Live (gemini-3.1-flash-live-preview, voice Aoede, live/voice_config.py:27,391)
  ↓ 24kHz PCM Audio (OUTPUT_SAMPLE_RATE 24000)
  ↓ _on_gemini inline_data 538 -> len<32 ignore, 32-160 keep -> b64 -> ws.send({"type":"audio", audio:b64}) 565
  ↓ index.html onmessage audio -> muskuPlayPcm(b64) OUT_RATE 24000 -> AudioBuffer -> speaker
  ↓ 🔊 Greeting Voice (real Aoede, no local TTS) + transcription bubble (both: model 692)
```

### 6.2 Files:Line for Greeting

| Function | File:Line | Note |
|---|---|---|
| `greetingText()` | `index.html:7587` | time-based |
| `get_respectful_start_greeting` | `personal_profile.py:67` | `name_resolver.resolve_greeting_term()` |
| `build_start_greeting_prompt` | `personal_profile.py:82` | 20 variants + `_LAST_GREETING` dedupe |
| `send_greeting(force)` | `live/musku_live_session.py:286` | `force=True` fresh, queue if no session |
| `send_start_greeting` | `live/browser_live_ws.py:176` | script-preserving per-uid |
| `run()` flush | `live/musku_live_session.py:235` | `force=True` + clear |
| `_on_browser` START GREETING | `live/musku_live_session.py:385` | `force=True` early return |
| `app.py /api/start` | `app.py:154` | preserves `greet`, sanitize 80 chars |
| `muskuPlayPcm` | `index.html:6379` | `OUT_RATE 24000` |
| `_pending_greetings` | `live/browser_live_ws.py:93` | `uid -> script|None` |
| `_greeted_time` grace | `musku_live_session.py:302,522` | `interrupted` ignored 3s after greeting |

### 6.3 4 Mandatory Fixes (Applied 2026-08-29, Still Active)

1. **Har START → 1 fresh** `force=True` + reset `finally: _greeted=False` `musku_live_session.py:268`.
2. **Gemini not ready → queue → auto send** `browser_live_ws.py:189` + `musku_live_session.py:235` + `index.html:7728` dual WS+HTTP.
3. **Mic not blocking** `index.html:7601,5240` fire-and-forget, greeting `speaking` while mic `listening` later.
4. **Existing pipeline same** `24kHz PCM WS muskuPlayPcm` no TTS, no grid/chat change.

**Constraints honored:** Grid `1fr 2fr 1fr` no change, chat `#chatFeed` no change, mic pipeline no change, local TTS no.

---

## 7. 🎙️ LIVE VOICE GENERATION (Shared with Greeting, Also Voice-to-Voice)

*Not greeting-only — same pipeline for ongoing voice chat.*

**Config** `live/voice_config.py:27` `DEFAULT_MODEL gemini-3.1-flash-live-preview`, `31 INPUT 16000 mono`, `37 OUTPUT 24000`, `77 FRAME 1280 (40ms)`, `72 INSTANT_VOICE 1`, `114 WS 0.0.0.0:8770` (or `$PORT`), `391 VOICE Aoede` (config.json `musku_voice` > env `GEMINI_LIVE_VOICE`).

**Connect** `musku_live_session.py:83 build_musku_connect_config(system_prompt, language)` → `SpeechConfig(Aoede)` + `LiveConnectConfig(response_modalities=[AUDIO], system_instruction, tools 2 decls, input/output transcription hi-IN via get_transcription_language_code)` → `client.aio.live.connect(model, config)` `228`, `status: connecting_gemini/connected/gemini_ready` `225`.

**Loop — Mic → Gemini:**
* Mic `index.html:6662` `getUserMedia echoCancellation` → `AudioContext 16000` + AudioWorklet `MicProcessor` (adaptive `micGain*micAdaptive targetRMS 0.05 adaptMax 12`, `Float→Int16`) → `appendMicPcm` → `WS {audio:b64 pcm16000}` 
* Server `musku_live_session.py:361` `_apply_mic_gain(MIC_INPUT_GAIN 1.0)` + `publish_pcm_meter` → `types.Blob(mime="audio/pcm;rate=16000")` → `send_realtime_input(audio)` → `WS_UPLOAD` telemetry

**Loop — Gemini → Speaker:**
* `_on_gemini:508` `server_content.model_turn.inline_data PCM b64` → `len<32 ignore` (keepalive), `32-160` tail still play (`_MIN_AI_PCM 160` was 480 tail-drop fix) → `{type:audio b64 24k}` → browser `AudioContext 24kHz` `muskuPlayPcm` → speaker + `AI_AUDIO_CHUNK` bus + `on_musku_busy`
* `output_transcription` `677` → `live_display_text` + `filter_unnecessary_laughter` → `merge_transcript` → `{transcription role:model}` bubble + `_last_model_text/time` for echo suppression
* `input_transcription` `567` → echo suppression (SequenceMatcher vs `_last_model_text` window `4s` greeting else `2.5s`, `good morning` prefix special) → `prepare_user_piece` + `merge_transcript` → `{transcription role:user}` + `record_last_user_message` + `maybe_save_user_name`
* `turnComplete` `719` → `record_last_musku_reply` → `asyncio.create_task(_persist_and_sync(user→[START greeting] if empty, reply))` + `on_musku_idle` + `{turnComplete}` + `TURN_COMPLETE` bus + `debug_telemetry`

**Tools:** `live_tools.py` `saveMemory` → `memory/store.py:66 save_memory` + `searchWebInfo` → `brain/search.py` web_search. Sequential `send_tool_response` (`musku_live_session.py:754` — parallel race fix: `openWebsite+playYouTube` double tab removed). PC-control → `get_upgrade_note(greeting_term)` via `persona/identity_policy.py`.

**Persona live updates:** `update_system_prompt` `318` realtime inject (`[INTERNAL INSTRUCTION ...]`), `detect_persona_mode` `407` relationship switch → `set_relationship_mode` + `get_live_system_prompt` new.

**Voice-to-Voice vs Greeting isolation:** Greeting branch early `return` `385` before normal `audio 361` / `text 380` handling → ongoing voice unaffected.

**Transcription language:** `voice_config.py:199 get_transcription_language_code` → `hi-IN` for `hinglish/hindi`, `en-IN` for `english`, env `MUSKU_TRANSCRIPTION_LANG` override. Both `input_audio_transcription` + `output_audio_transcription` set.

---

## 8. 💬 TEXT CHAT FLOW (Separate from Live Voice)

```
index.html #txtCmd Enter (TYPE COMMAND)
  → fetch(`${origin}/api/chat`, {method:POST, body:{text, uid, key, token}, headers:{Authorization:Bearer idToken, X-Musku-Key}})
  → app.py:do_POST /api/chat (or WSGI handler:508)
    1. clen >20KB →413; raw_text >2000 →400; strip [INTERNAL/[SYSTEM injection (app.py:240)
    2. token = extract_token(headers, body) // Bearer || body.token (auth_verify.py:166)
    3. uid = resolve_verified_uid(token, body.uid) → if None →401 (REQUIRE_AUTH true)
    4. if ! _rate_ok(uid) (30/min per uid, window 60s, app.py:75) →429 Retry-After 60
    5. raw_key = body.key || X-Musku-Key header → save_config({gemini_api_key:raw_key}, uid) // dual file+Firestore encrypted
    6. set_uid(uid) // tenant_ctx ContextVar — scopes ALL later paths (memory/paths, store, chat, turn_context)
    7. cfg = load_config(uid); user_name = cfg.user_name
    8. b = MuskuBrain(user_name, config=cfg); reply = b.get_response(text)
         // brain_core.py: MuskuBrain.get_response → emotion→memory routed→conversation pending→search mode→_generate_reply
         // if "Desktop control not active" / "directly control nahi" in reply OR empty → fallback:
         //   _gemini_chat([{role:"system", content: boss_instruction(user_name, cfg.language)},
         //                 {role:"user", content: text}], api_key=cfg.gemini_api_key)
         //   boss_instruction = persona_composer.build_persona_prompt (aap lock, relationship_mode)
         //   _gemini_chat → brain/llm.py gemini_chat with GEMINI_MODEL=gemini-3.5-flash-lite + backup, thinking_budget 0, 14 RPM
    9. → {"reply": reply} JSON 200 + CORS headers (X-Content-Type-Options nosniff etc.)
  → Browser renders #chatFeed bubble + js/storage queue saveMessage + backup
  → Async persist: brain/memory_bridge.py: save_chat_log → memory/chat.py save_chat (ring daily) + memory/turn_context + conversation.record_exchange + consolidate background (14 turns → ADD/UPDATE/REMOVE)
```

**Brain delegation detail `brain_core.py:2709`:**
* `DATA_DIR/PROFILE_FILE/...` all imported from `memory/paths.py` (single source, not defined in brain_core).
* `GEMINI_MODEL gemini-3.5-flash-lite` + `GEMINI_MODEL_BACKUP gemini-3.5-flash`, `GEMINI_MAX_PER_MIN 10` deque throttle (`brain_core.py:952`), `brain/llm.py:14` RPM mirror.
* `_HINGLISH_DEVA` dict 350+ words (`brain_core.py:209`) merged with `musku_data/musku_vocab_master.json` 5000+ words via `_load_master_vocab:917`, `deva_to_hinglish` `819` uses dynamic reverse dict + `indic_transliteration` IAST fallback + final char-map guarantee no Devanagari remains in Roman bubbles.
* `ATTITUDE_GUIDANCE` nakhra/caring/normal (`brain_core.py:102`), `STOP_COMMANDS` barge keywords (`:110`), `LIVE_MIC_LEVEL` gauge (`:129`).
* `execute_system_command` stub only returns upgrade note with per-user greeting term — never controls OS.

**Vercel path identical** via `app.py:handler()` WSGI (same rate-limit, same auth, same Gemini fallback, same headers).

---

## 9. 💾 CHAT STORAGE (3-LAYER) — DUAL TRUTH

### Layer 1 — Firestore PRIMARY + dual source `firebase/firestore.py:139`

```
users/{uid}/
  ├── profile/main          {user_name, language, relationship_mode, ...}  save_user_profile_fs
  ├── preferences/main      {likes, ...}
  ├── memory/{category}     {items: [...], updated_at: SERVER_TIMESTAMP}  save_categorical_memory_fs (15 categories)
  ├── reminders/{id}        {fact, due_at, ...}
  ├── conversations/{date}/turns/{autoId}  {user, musku, timestamp: SERVER_TIMESTAMP, date, meta}  save_chat_turn_fs
  └── messages/{msgId}      individual messages

users/{uid} api_keys       gemini key hint (firebase/api_keys.py:72)  load_api_key_fs / save_api_key_fs
firestore.rules: request.auth.uid == userId (18 lines) — no cross-uid read
```

`get_firestore_client()` lazy `firebase_admin.initialize_app()` — graceful degrade if no creds (logs warning, returns None, local JSON becomes truth).

### Layer 2 — Local JSON `memory/paths.py:234` + `memory/chat.py:296` + `memory/store.py:447`

```
For uid != "owner":
  musku_users/{uid}/musku_data/
    ├── user_profile.json (profile), relations_memory.json, preferences_memory.json, passion_memory.json,
    │   places_memory.json, pc_command_memory.json, finance_memory.json, ideas_memory.json, health_memory.json,
    │   inventory_memory.json, learning_memory.json, tasks_memory.json, emotional_memory.json, goal_memory.json,
    │   behavior_memory.json, memory_index.json (dedup hash key→category), recent_turns.json (ring 20),
    │   rules_config.json, turn_context.json, conversation_state.json, chat_summary.txt (800 chars), reminders.json
  musku_users/{uid}/musku_chat/
    └── 2026-09-01.json  (daily file, cap 200 entries, ring recent_turns 20)

For uid == "owner" (legacy local):
  musku_data/ + musku_chat/  (BASE_DIR) + chat_summary.txt at BASE_DIR

Constants: CONTEXT_WINDOW 20, MEMORY_MAX_PER_CATEGORY 60, HISTORY_RECALL_WINDOW 30
IO: FILE_LOCK global threading.Lock, atomic _write_json via tempfile+fsync+os.replace (paths.py + user_context.py:304)
Proxies: _LiveFileMap / _LiveCatFiles — from imports stay live per ContextVar uid (PEP562 __getattr__)
```

**Category map `memory/paths.py:28`:**
`relations, places, passion, preferences, pc_command, finance, ideas, health, inventory, learning, tasks, emotional, goal, behavior, profile(→important_facts)` — each file `MEMORY_FILE_MAP` keyname `MEMORY_KEY_NAMES`.

### Layer 3 — IndexedDB Browser `js/storage/db.js:146`

```
DB: MUSKU_DB v1
Stores (7): conversations (key conversation_id, index date_key)
            messages (key message_id, index conversation_id)
            memory (category)
            user_profile
            persona_state
            projects
            metadata
Helpers: queue.js 60 P0-3 priority offline queue
         backup.js 98 export JSON + restore
         historyService.js 79 daily fetch + HISTORY_RECALL_WINDOW
Tests: js/tests/runner.js + storage-*.test.js
```

### Write Path (single, both text + voice converge)

```
Text:  brain/memory_bridge.py: save_chat_log(b, user, reply, uid) 
         → _mchat.save_chat(date, entry) → ring recent_turns.json 20 + daily file 200/day + calendar json
         → turn_context.update_after_turn(uid) + conversation.record_exchange
         → _consolidate_background(user_text, uid) async thread:
             memory/consolidate.py process_conversation_slice (14 turns window)
             → Gemini LLM → transactions [{action:ADD|UPDATE|REMOVE, id, category, text}]
             → memory/store.py apply_transactions → save_memory / update / remove
             → prune_memory stale 14d if needed
         → chat_summary via _summarize_old_history if > CONTEXT_WINDOW
         → firestore save_chat_turn_fs (best-effort)

Voice: musku_live_session.py:762 _persist_and_sync(user, reply)
         → asyncio.to_thread(_persist_turn_and_consolidate) 772 — re-establishes set_uid(uid) (ContextVar lost in thread)
         → save_chat_log(None, user, reply, consolidate=False, uid) + _consolidate_background(user, uid)
         → store.load_all() → ws.send({type:"memory_sync", memories: updated}) → browser IndexedDB sync
         → firestore save_chat_turn_fs + save_categorical_memory_fs dual
```

### Read Path (injected into Live prompt per connect)

`live/voice_config.py:238 get_live_memory_block(uid)` merges:
1. `turn_context.get_live_turn_context_block(uid)` — last_user/musku, pending riddle/question, correct streak block `2,3,5,8,13`
2. `turn_context.get_streak_prompt_block` — praise injection
3. `store.format_live_memory_card(max 6/cat)` — ordered `profile, relations, passion, emotional, goal, behavior, preferences, places, finance, ideas, health, learning, tasks` + `MEMORY_COGNITIVE_PRINCIPLES` (human-like, never say "database")
4. `chat.load_recent_memory_context()` — recent 10 turns
5. `chat.load_chat_summary()` — rolling summary older
6. `last_question` PREVIOUS-REPLY RULE — `ha batao/continue karo/kya bol rahi thi` → repeat `LAST MUSKU REPLY` verbatim
7. `MEMORY RULES` — `last time kya kiya / yaad hai` → answer from saved facts, no guess

Injected as `base persona + "\n\n" + mem` via `get_live_system_prompt:312`.

---

## 10. MULTI-TENANT ISOLATION

```
auth_verify.py  extract_token(headers,body) → verify_id_token(RS256) → resolve_verified_uid(token,client_uid)
     ↓ verified uid (never client-supplied alone in prod)
tenant_ctx.py   ContextVar musku_uid + safe_uid() regex [^A-Za-z0-9_-] + ..//\ reject + 64 char cap
     ↓
user_context.py set_uid(uid) → load_config(uid) per-uid:
     Priority Firestore api_keys (cross-device) → file musku_users/{uid}/config.json → DEFAULT_CONFIG
     save_config merges + encrypts gemini_api_key via crypto_utils + dual Firestore hint
     detect_persona_mode / set_relationship_mode per-uid
     extract_uid_from_query / headers helpers
memory/paths.py PEP562 __getattr__ — every file symbol re-resolves via current ContextVar uid
     ↓
All runtime per-uid: turn_context.py, conversation.py, emotion.py, store.py, chat.py,
                    browser_live_ws._sessions dict uid→MuskuLiveSession (one-session-per-uid guard 509),
                    musku_live_session re-set_uid in to_thread 776
```

| Risk | Guard | File:Line |
|---|---|---|
| Spoof another uid | Token must verify when `firebase_admin` installed; `resolve_verified_uid` returns `None` → 401/1008 | `auth_verify.py:141`, `firebase/auth.py:37` |
| Path traversal | `safe_uid` rejects `..`, `/`, `\`, caps 64 | `tenant_ctx.py:39` |
| Cross-user memory leak | `__getattr__` per-uid, `_LiveFileMap` live proxy, `ContextVar` | `memory/paths.py:198` |
| Double session overwrite | `_sessions[ukey].active` guard → `already active` 1008 | `browser_live_ws.py:534` |
| `to_thread` uid loss | Re-`set_uid(uid)` inside thread | `musku_live_session.py:776` |

---

## 11. PERSONA ENGINE

**Composer `persona/persona_composer.py:50`**
`build_persona_prompt(boss_name, preferred_title, relationship_mode, language)` merges `core_personality + identity_policy (Musku name lock, MUSKU_CREATOR S2, feminine enforcement) + relationship profile + tone_engine + drift_guard + language_policy`. Boss word purged → `aap`.

**Relationship `persona/relationship_engine.py:22`**

| Mode | Aliases | Vibe |
|---|---|---|
| `best_friend` (default) | best friend, bestie, bff, dost, friend | Loyal, cute, chulbul, flirty, energetic |
| `jigri` | jigri, jigri dost, yaar, buddy, bro | Relaxed, bold, masti, fast |
| `beti` | beti, daughter, bachi | Sweet, innocent, caring |
| `caring` | caring, companion, supporter | Warm, calm, protective + chulbul |
| `girlfriend` | girlfriend, gf, partner, life partner, soulmate, jaan | Romantic, nakhra, loyal, cute |
| *custom* | any `raw len>=2` not in modes | Dynamic `CUSTOM {Title}` profile generated on fly |

Any `"meri X ban"` / `"X ban jao"` / open-ended `"X ban"` (2-20 chars) → custom dynamic profile (`relationship_engine.py:115`).

**Switch:** `user_context.py:87 detect_persona_mode(text)` checks `PERSONA_KEYWORDS` then `relationship_engine` alias → `set_relationship_mode(uid, mode)` persist, then `get_live_system_prompt(..., relationship_mode=mode, uid)` + `update_system_prompt` live inject + friendly `PERSONA_SWITCH_REPLY` voice confirm (`musku_live_session.py:407`).

**Name resolver `persona/name_resolver.py:155`**
`resolve_greeting_term()` → saved `user_name` or `dear`; `maybe_save_user_name(text)` catches `"mujhe X bulao" / "my name is X" / "call me X"` via regex and persists via `user_context.save_config`.

**Abuse policy `persona/abuse_policy.py:104`**
`is_abusive(text)` → `get_polite_boundary_reply(uid)` deterministic; `POLITE_BOUNDARY_BLOCK` injected into every system prompt (`voice_config.py:225`, `personal_profile.py`). In live voice, abusive `type:text` bypasses Gemini and returns polite reply directly + persists turn (`musku_live_session.py:454`).

**Other:** `core_personality.py:23` CORE_PERSONALITY_TRAITS, `tone_engine 19`, `drift_guard 15`, `persona_cache 31`, `address_system 27`.

---

## 12. BRAIN — DELEGATION MAP

```
MuskuBrain(user_name, config)  brain_core.py:2709 facade
  ├── brain/llm.py        get_gemini_client(api_key) per-key cache + acquire_gemini_slot 14 RPM + gemini_chat
  ├── brain/router.py     classify_conversational_intent, is_fast_pc_command() == False (web)
  ├── brain/conversation.py  record_exchange(topic/app/action/pending_question) uid-scoped conversation_state.json
  ├── brain/memory_bridge.py save_chat_log + _consolidate_background (14 turns → LLM transactions) + auto_extract_and_learn
  ├── brain/emotion.py    emotion detection
  ├── brain/response.py   post-processing
  ├── brain/search.py     web_search (Google CSE)
  ├── memory/*            (see §9)
  ├── persona/*           (see §11)
  └── language_policy.py  normalize_language + get_language_persona_rules
```

**Gemini fallback path (text chat):** `app.py:279` → `_gemini_chat([{system: boss_instruction},{user: text}], api_key=per-uid)` → `brain/llm.py` / `brain_core.py:_gemini_chat` with `thinking_budget 0`, `GEMINI_MODEL gemini-3.5-flash-lite`, backup `gemini-3.5-flash` on 429/empty.

**Transliteration:** `_HINGLISH_DEVA` + `musku_vocab_master.json` → `deva_to_hinglish(text)` (`brain_core.py:819`) for Roman bubbles when profile=`hindi` but display is `hinglish`. Covers 5000+ words; fallback `indic_transliteration` IAST → `_itrans_to_hinglish`, then char-map guarantee no Devanagari leaks.

---

## 13. FRONTEND — `index.html` 8412 lines + `js/` + `auth.js`

* **Layout:** 3-col grid `1fr 2fr 1fr` (§4), LEFT gauges (SYSTEM SOUND APPS BRAIN LEVEL), CENTER `.stage 450px` gif `Hello.gif/Normal.gif/Talking*.gif` + `.eq` 16 bars + `#startBtn`, RIGHT avatar + `TYPE COMMAND #txtCmd` + `LIVE CHAT #chatFeed` + `LIVE STATUS`.
* **Themes:** 13 themes `ui_theme.css` (amethyst/oceanic/obsidian/emerald/monochrome/crimson/sunset/golden/cyberpunk/aurora/holographic/chrome/pink) via `data-theme`.
* **Audio Worklet:** `MicProcessor 7576` adaptive `micGain*micAdaptive targetRMS 0.05 adaptMax 12`, `captureRate resample linear 48k→16k`, `Float→Int16`, `appendMicPcm` → `WS {audio:b64}` + `pywebview.api.on_browser_mic_chunk` meter.
* **Playback:** `muskuPlayPcm(b64) 6379` `AudioContext 24kHz` decode → `AudioBuffer` → `GainNode musku_voice_gain 2.4` → speaker. Queue `OUTPUT_QUEUE_MAX 24` instant.
* **Chat:** `#txtCmd keydown Enter` → `POST /api/chat` → bubble `chatFeed` → `js/storage queue saveMessage` → `backup.js`.
* **Connect:** `connectLiveWs()` builds `ws://host:8770/live?uid=&token=&key=` (local) or `wss://host:$PORT/live` (deployed same-origin) + `voice_config` gain on open, `onmessage {audio|transcription|turnComplete|memory_sync|voice_config|error|status}` handlers `6744`.
* **Auth UI `auth.js:1069`:** Firebase Google Sign-In `musku-ai` project, `localStorage musku_id_token` refresh `getIdToken(true)` every 50m, `collectAndStoreTrace` → `musku_traces/{uid}` (device/IP/location), `musku_users/{uid}` + `musku_users_by_email`, plan `FREE 7D once per Firebase UID` + Pro `MUSKU-XXXX` 120-bit `crypto.getRandomValues` + `SHA256+HMAC hmacForHash(secret:hash)` + rate limit `5/5min` localStorage, stored `musku_keys_hash/{hash}` opaque + `musku_activations/{uid}`.

---

## 14. API ENDPOINTS — `app.py:690` + `browser_live_ws.py:595`

| Method | Path | Auth | Purpose | Payload / Response | Codes |
|---|---|---|---|---|---|
| `POST` | `/api/start` | `resolve_verified_uid` 401 | Queue greeting before WS connects | `body {uid, greet\|script(80 chars), token}` sanitized no `[INTERNAL/SYSTEM/IGNORE` → `send_start_greeting(uid,script)` → `{"status":"ok"}` | 413 >20KB, 401, 500 |
| `GET` | `/api/start` | none | Health debuggability | `{"status":"ok"}` | 200 |
| `POST` | `/api/chat` | verified uid + `_rate_ok` 30/min | Text chat (no voice) | `body {text(max2000), uid, key, token}` → `MuskuBrain.get_response` → fallback `_gemini_chat` → `{"reply": reply}` | 413/400/401/429/500 |
| `POST` | `/api/save-key` | verified uid | BYOK persist (encrypted dual write) | `body {key\|gemini_api_key, uid, token}` regex `^AIza[0-9A-Za-z\-_]{35,}$` → `save_config({gemini_api_key:key},uid)` → `{"status":"ok", hint:"AIza..xxxx"}` | 413/401/400 invalid_key |
| `GET` | `/health`, `/api/health` | none | PaaS liveness (RunxBuild/HF/Render) | `{"status":"ok","service":"musku-2.0"}` | 200 |
| `GET` | `/`, `/index.html`, `/ui_theme.css`, `/auth.js`, `/js/*`, `/img/*`, `/favicon.ico`, `/how-to-use.html`, `/activate.html`, `/admin.html`, `/signup.html` | none (blocked sensitive) | Static UI | MIME + CORS + `Cache-Control max-age 3600` + security headers; blocked `config.json,.env,crypto_utils.py,musku_data,musku_users,musku_chat,.git,debug_greeting.log` + `..` traversal | 404 if outside BASE_DIR |
| `OPTIONS` | `*` | none | CORS preflight | `Allow-Methods GET POST OPTIONS`, `Allow-Headers Content-Type, Authorization, X-Musku-Key, X-Musku-Uid` | 200 |
| `WS` | `/live`, `/live/` | `verify_firebase_token` + `resolve_verified_uid` → 1008 | Full-duplex voice | Query `?token=&uid=&key=` + `Authorization`; subprotocol JSON: `→ {audio:b64 pcm16k}`, `{video:b64 jpeg}`, `{text}`, `{toolResponse}`, `← {type:audio b64 24k}`, `{transcription role:user\|model}`, `{status}`, `{turnComplete}`, `{interrupted}`, `{memory_sync}`, `{voice_config gain}`, `{debug_telemetry}`, `{error}` | 1008 origin/path/already active/api key missing |
| `WS` | `process_request HTTP` single-port | delegates to `app.handler` | PaaS single `$PORT` multiplex | Path split `_LIVE_PATHS` → WS else WSGI environ build | 500 fallback |
| — | Realtime DB (browser direct via Firebase SDK, not app.py) | Firebase rule | Traces & activation | `musku_traces/{uid}`, `musku_users/{uid}`, `freeClaims/{uid}`, `musku_keys/{key}`, `musku_keys_hash/{hash}`, `musku_activations/{uid}` | — |

**Common guards:** `MAX_API_BODY 20KB` → 413, `MAX_CHAT_TEXT 2000` → 400, `BLOCKED_STATIC` + `ALLOWED_STATIC_PREFIXES`, `X-Content-Type-Options nosniff`, `X-Frame-Options DENY`, `Referrer-Policy strict-origin`, CORS `Vary: Origin`.

---

## 15. AUTH FLOW

```
Browser auth.js: Firebase Google Sign-In (project musku-ai)
  → saveUser({uid, displayName, email, photo}) + collection musku_users/{uid}, musku_users_by_email/{email}
  → localStorage musku_id_token refreshed every 50m via getIdToken(true)
  → collectAndStoreTrace → Realtime DB musku_traces/{uid} (device/IP/location)

Every HTTP POST & WS handshake includes:
  token = Authorization: Bearer <idToken> || body.token || body.idToken || query ?token=

Server auth_verify.py:178 verify_id_token(token)
  → split JWT header.payload.sig → _get_key(kid) from Google x509 cache (CERT_URL, 1h TTL)
  → RSAPublicKey.verify(PKCS1v15, SHA256) + checks exp/aud==musku-ai/iss==securetoken.google.com/musku-ai
  → returns verified uid (uid||sub)

  resolve_verified_uid(token, client_uid)
    → if token present: MUST verify when firebase_admin installed (prod) → invalid → None → 401/1008
    → if firebase_admin NOT installed (local dev) → fallback to client_uid (prevents stale cached idToken reconnect loop)
    → if no token + REQUIRE_AUTH true (default) → None → 401 (fail-closed)
    → if REQUIRE_AUTH false (explicit local dev) → trust client_uid

  firebase/auth.py verify_firebase_token(token, fallback_uid) — thin wrapper authoritative fallback

  UID then = storage scoping EVERYWHERE (tenant_ctx ContextVar) — never trust client_uid alone in prod
```

---

## 16. CONFIG KNOBS — `live/voice_config.py:421` + `config.json` + env

| Key | Default | Source | Meaning |
|---|---|---|---|
| `GEMINI_LIVE_MODEL` | `gemini-3.1-flash-live-preview` | env `GEMINI_LIVE_MODEL` | Live voice model |
| `GEMINI_LIVE_VOICE` / `musku_voice` | `Aoede` | env `GEMINI_LIVE_VOICE` > `config.json musku_voice` | Female voice (VOICES: Kore Leda Orus Zephyr Puck Charon Fenrir Aoede) |
| `musku_voice_gain` | `2.4` (voice_config) / `1.8` (DEFAULT_CONFIG) | `config.json` | Speaker browser GainNode |
| `BROWSER_LIVE_WS` | `True` | voice_config | Enable WS server |
| `BROWSER_LIVE_WS_HOST` | `0.0.0.0` | env `MUSKU_LIVE_WS_HOST` | WS bind |
| `BROWSER_LIVE_WS_PORT` | `8770` or `$PORT` if env not set | env `MUSKU_LIVE_WS_PORT` || `PORT` | WS port (single-port PaaS auto) |
| `INPUT_SAMPLE_RATE` | `16000` | voice_config | Mic → Gemini |
| `OUTPUT_SAMPLE_RATE` | `24000` | voice_config | Gemini → speaker |
| `INPUT_CHANNELS` | `1` mono | voice_config | |
| `FRAME_BYTES` | `1280` | calc `16k*2*1*40ms` | |
| `CHUNK_DURATION_MS` | `40` | voice_config | Mic chunk |
| `INSTANT_VOICE_MODE` | `1` | env `MUSKU_INSTANT_VOICE` | Low latency (24 queue vs 48) |
| `OUTPUT_QUEUE_MAX` | `24` instant else `48` | env `MUSKU_OUTPUT_QUEUE` | Speaker queue |
| `OUTPUT_FRAMES_PER_BUFFER` | `128` instant else `256` | env `MUSKU_OUTPUT_FRAMES` | |
| `SEND_QUEUE_MAX` | `24` instant else `80` | env `MUSKU_SEND_QUEUE` | Mic → Gemini queue |
| `SPEAKER_DRAIN_IDLE` | `0.08` instant else `0.25` | env `MUSKU_SPEAKER_DRAIN_IDLE` | Drain → LISTENING |
| `TURN_FLUSH_TIMEOUT` | `0.08` instant else `2.0` | env `MUSKU_FLUSH_TIMEOUT` | turnComplete flush cap |
| `INSTANT_LISTEN_RESTORE` | `1` if instant+mic | env `MUSKU_INSTANT_LISTEN` | TurnComplete instant LISTENING |
| `MIC_ECHO_CANCELLATION` | `1` | env `MUSKU_MIC_ECHO_CANCEL` | getUserMedia echoCancellation |
| `MIC_NOISE_GATE_ENABLED` | `False` | env | Fan noise optional |
| `MIC_NOISE_FLOOR` | `0.008` | env `MUSKU_MIC_NOISE_FLOOR` | |
| `MIC_SPEECH_RMS` | `0.012` | env `MUSKU_MIC_SPEECH_RMS` | |
| `MIC_INPUT_GAIN` | `1.0` | env `MUSKU_MIC_GAIN` | Python side boost (JS already 3.0) |
| `MIC_METER_GAIN` | `2.8` | env `MUSKU_MIC_METER_GAIN` | Meter display gain |
| `JS_MIC_GAIN` | `3.0` | env `MUSKU_JS_MIC_GAIN` | JS adaptive base (Weak mics ~1% → 0.05 targetRMS) |
| `BROWSER_MIC_ENABLED` | `True` | voice_config | |
| `MUSKU_INLINE_LIVE` | `1` if `BROWSER_LIVE_WS` | env | Thin bridge |
| `MUSKU_LIVE_DEBUG` | `0` | env | Verbose logs |
| `ECHO_GATE_WHILE_SPEAKING` | `1` | env `MUSKU_ECHO_GATE` | Blocks mic→Gemini during SPEAKING |
| `LOCAL_BARGE_IN_ENABLED` | `1` | env `MUSKU_LOCAL_BARGE_IN` | Local barge detector |
| `VOICE_ROUTER_ENABLED` | `0` | env `MUSKU_VOICE_ROUTER` | |
| `INSTANT_SEARCH_HOOK` | `0` | env `MUSKU_INSTANT_SEARCH_HOOK` | Parallel search inject (off) |
| `LIVE_TOOLS_ENABLED` | `1` | env `MUSKU_LIVE_TOOLS` | saveMemory/search |
| `LIVE_TOOLS_SLIM` | `1` if instant | env `MUSKU_LIVE_TOOLS_SLIM` | |
| `SCREEN_SHARE_ENABLED` | `0` instant else `1` | env `MUSKU_SCREEN_SHARE` | |
| `BARGE_IN_RMS_THRESHOLD` | `0.12` | env `MUSKU_BARGE_RMS` | |
| `VOICE_STUCK_TIMEOUT` | `8.0` / speaking `10.0` | env `MUSKU_STUCK_TIMEOUT` | Gate stuck fallback |
| `LIGHT_STARTUP` | `1` if instant | env `MUSKU_LIGHT_STARTUP` | |
| `LIVE_SILENCE_DURATION_MS` | `220` instant else `500` | env `MUSKU_SILENCE_MS` | VAD silence before reply |
| `LIVE_END_SPEECH_SENSITIVITY` | `high` | env `MUSKU_END_SPEECH_SENS` | |
| `USER_IDLE_CHECKIN_SECS` | `60` | env `MUSKU_IDLE_CHECKIN_SECS` | Silent check-in |
| `PROACTIVE_BREAK_MINS` | `30` | env `MUSKU_BREAK_MINS` | Health nudge |
| `PROACTIVE_WATER_MINS` | `45` | env `MUSKU_WATER_MINS` | |
| `PROACTIVE_EYE_REST_MINS` | `50` | env `MUSKU_EYE_REST_MINS` | |
| `PROACTIVE_STRETCH_MINS` | `60` | env `MUSKU_STRETCH_MINS` | |
| `GEMINI_MODEL` (text) | `gemini-3.5-flash-lite` + backup `gemini-3.5-flash` | `brain/llm.py:13`, `brain_core.py:202` | Text fallback |
| `GEMINI_MAX_PER_MIN` | `14` (llm.py) / `10` (brain_core) | | RPM throttle |
| `CONTEXT_WINDOW` | `20` | `memory/paths` | Recent turns ring |
| `MEMORY_MAX_PER_CATEGORY` | `60` | `memory/paths` | Cap per category |
| `HISTORY_RECALL_WINDOW` | `30` | `memory/paths` | Last-time query |
| `REQUIRE_AUTH` | `true` | env (app.py:20) | Fail-closed auth |
| `ALLOWED_ORIGIN` | `https://musku-ai.web.app, https://musku-ai.firebaseapp.com, http://localhost:8000` or CSV or `*` dev | env | CORS/WS origin allowlist |
| `FIREBASE_PROJECT_ID` | `musku-ai` | env | |
| `PORT` | `8000` | env | HTTP; WS shares if single-port |
| `language` | `hinglish` | `config.json` per-uid | hi-IN/en-IN/hinglish → transcription + persona |
| `relationship_mode` | `best_friend` | per-uid config | best_friend/jigri/beti/caring/girlfriend/custom |
| `user_name` | `S2` | `config.json` | Greeting term via name_resolver |

`config.example.json` exposes: `user_name, gemini_api_key, google_search_key, google_cx, language, musku_voice, musku_voice_gain, duck_volume, ui_settings {theme crimson, design energy}`.

---

## 17. SECURITY BOUNDARIES

| Layer | Enforcement | File:Line |
|---|---|---|
| **Auth fail-closed** | `REQUIRE_AUTH=true` default → `resolve_verified_uid` returns `None` → 401/1008; `/health` exempt | `app.py:20`, `auth_verify.py:44` |
| **RS256 verify** | Google x509 `securetoken@system.gserviceaccount.com` cached 1h, checks `exp/aud/iss/sub/uid`, `kid` fetch | `auth_verify.py:62` |
| **Never trust client uid** | Verified uid scoped; fallback only when `firebase_admin` missing (local dev stale token loop) | `auth_verify.py:141` |
| **Per-uid isolation** | `ContextVar` + `safe_uid` regex + `memory/paths` dynamic + `_sessions` dict + `turn_context`/`store`/`chat` uid-aware + `to_thread re-set_uid` | `tenant_ctx.py:39`, `memory/paths.py:98`, `musku_live_session.py:776` |
| **One session per uid** | `_sessions[uid]` guard → `already active` 1008 | `browser_live_ws.py:534` |
| **CORS/CSWSH** | `_allowed_origins` + `*.vercel.app/*.runxbuild.app` wildcard + `Vary: Origin`; WS `_handler` Origin check 425 | `app.py:44`, `browser_live_ws.py:425` |
| **Payload limits** | `MAX_API_BODY 20KB`, `MAX_CHAT_TEXT 2000` → 413/400; injection strip `[INTERNAL/[SYSTEM`; script 80 chars | `app.py:38` |
| **Rate limit** | In-memory per-uid `_RATE` 30/min window 60s → 429 `Retry-After 60` | `app.py:75` |
| **Sensitive files block** | `BLOCKED_STATIC {config.json,.env,crypto_utils.py,musku_data,musku_users,musku_chat,.git,debug_greeting.log}` + `ALLOWED_STATIC_PREFIXES` + `normpath` traversal `startswith BASE_DIR` | `app.py:40,413` |
| **Security headers** | `X-Content-Type-Options nosniff`, `X-Frame-Options DENY`, `Referrer-Policy strict-origin-when-cross-origin`, CSP `default-src 'self'; script-src 'self' https://www.gstatic.com; connect-src 'self' wss: generativelanguage.googleapis.com` | `app.py:138`, `vercel.json:4` |
| **Encrypted BYOK** | Fernet PBKDF2 machineId, 10-layer `gAAAA` re-encrypt, `SENSITIVE_KEYS` gemini/google, Firestore hint `AIza...` prefix | `crypto_utils.py:1`, `user_context.py:21` |
| **Tool boundary** | Live tools ONLY `saveMemory` + `searchWebInfo`; PC/image/code → upgrade note; `is_fast_pc_command false` | `live/live_tools.py:1`, `brain/router.py:54` |
| **Abuse policy** | `is_abusive` + `POLITE_BOUNDARY_BLOCK` injected into all prompts; abusive text bypasses Gemini → deterministic polite reply | `musku_live_session.py:454`, `voice_config.py:225` |
| **API key validation** | Regex `^AIza[0-9A-Za-z\-_]{35,}$` | `app.py:324,613` |
| **HMAC activation** | `MUSKU-XXXX` 120-bit CSPRNG `crypto.getRandomValues`, `SHA256+hmacForHash(secret:hash)`, 5/5min localStorage, `musku_keys_hash/{hash}` opaque | `auth.js:335` |

---

## 18. `realtime/` — LEGACY LANE (NOT in browser inline path, but present)

`realtime/event_bus.py` pub/sub (`AI_AUDIO_CHUNK, USER_SPEECH_PARTIAL/FINAL, TURN_COMPLETE, RIDDLE_STREAK`), `state_machine SystemState`, `gate_controller`, `orchestrator`, `session_controller`, `voice_supervisor`. Used by old desktop transport (`live/musku_live_session.py:18` imports with `_DummyBus` fallback). In browser inline web path, `browser_live_ws` + `musku_live_session` are authoritative — `realtime` is not active but kept for desktop parity.

---

## 19. HOW TO RUN

```bash
cd musku-2.0
pip install -r requirements-server.txt
python app.py            # http://localhost:8000 + ws://localhost:8770/live
# or single-port PaaS: PORT=8000 python app.py  → ws://host:$PORT/live + https://host:$PORT/
```

Text-only Vercel via `app.py:handler` (no WS server, chat only). `config.json` crash-proof + atomic write.

**Deploy see `DEPLOY.md:80`:** Oracle Always-Free best (2 AMD/4 ARM VMs, never sleeps), Fly.io 3 VMs free, Firebase Hosting static only (needs Cloud Run paid for backend), `deploy/oracle_setup.sh` + `deploy/musku.service` + `deploy/nginx_musku.conf` → nginx TLS + `nginx` proxies `/` → `:8000` and `/live` → `:8770`. Persistent volume must mount at `/app/musku_users` (or `musku_users/<uid>/` lost on restart).

---

## 20. TESTING

```bash
python -m unittest discover -s tests
# tests: test_auth_verify, test_multitenant, test_multitenant_isolation, test_persona_engine, test_name_resolver, conftest
node js/tests/runner.js
# js/tests: storage-*.test.js via runner.js
python -c "import live.voice_config as c; assert c.OUTPUT_SAMPLE_RATE==24000; assert c.INPUT_SAMPLE_RATE==16000"
python -c "from live.musku_live_session import MuskuLiveSession; assert 'force' in MuskuLiveSession.send_greeting.__code__.co_varnames"
python -c "from memory.paths import DATA_DIR; print(DATA_DIR)"
```

Greeting manual: `START` → WS `{"text":"[INTERNAL - START GREETING: Good morning dear]"}` → log `Gemini connected` → WS `{"type":"audio"}` → Aoede 24kHz + bubble. `STOP→START` 3× should give fresh variant (20 pool, dedupe), mic denied still greeting (fire-and-forget). Voice-to-voice: speak after greeting → `input_transcription` → `model_turn audio+output_transcription` → `turnComplete` → `memory_sync`.
