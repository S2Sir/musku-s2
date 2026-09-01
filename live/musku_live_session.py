"""musku_live_session.py — Musku thin Gemini Live bridge.

Ek browser /live WebSocket = ek Gemini session. Audio seedha Gemini ↔ browser.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from typing import Any

from live import voice_config as cfg
from live.display_filter import live_display_text
from live.live_tools import build_function_declarations, resolve_live_tool
try:
    from realtime.event_bus import bus
except Exception:
    class _DummyBus:
        def publish(self, *args, **kwargs): pass
        def subscribe(self, *args, **kwargs): pass
    bus = _DummyBus()

logger = logging.getLogger("MUSKU.Live")

def _dbg_log(msg):
    # Only when MUSKU_LIVE_DEBUG=1 — warna spam (har audio chunk pe [GEMINI] log)
    if not bool(getattr(cfg, "MUSKU_LIVE_DEBUG", False)):
        return
    try:
        import os
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        p = os.path.join(base, "debug_greeting.log")
        with open(p, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass
    try:
        print(msg, flush=True)
    except Exception:
        pass


def _apply_mic_gain(pcm: bytes) -> bytes:
    """Quiet mics (headset) ko boost karke Gemini VAD tak pahunchao.

    Meter apna display-gain lagata hai (isliye meter hilta hai), par inline
    Live path me audio RAW jata tha — yahan MIC_INPUT_GAIN lagta hai.
    """
    gain = float(getattr(cfg, "MIC_INPUT_GAIN", 1.0))
    if gain <= 1.01 or not pcm:
        return pcm
    n = len(pcm) // 2
    if n <= 0:
        return pcm
    try:
        import struct
        samples = struct.unpack(f"<{n}h", pcm[: n * 2])
        boosted = tuple(max(-32768, min(32767, int(s * gain))) for s in samples)
        return struct.pack(f"<{n}h", *boosted)
    except Exception:
        return pcm

try:
    from google import genai
    from google.genai import types
    _HAVE_GENAI = True
except ImportError:
    _HAVE_GENAI = False
    genai = None  # type: ignore
    types = None  # type: ignore

_MIN_AI_PCM = 160  # greeting chunk tail ~3ms bhi play karo — 480 se pura vakya ka tail drop ho raha tha
_LIVE_DEBUG = bool(getattr(cfg, "MUSKU_LIVE_DEBUG", False))


def _live_dbg(msg: str):
    if _LIVE_DEBUG:
        print(msg)


def build_musku_connect_config(system_prompt: str, language: str = "hinglish"):
    """Musku Live connect — default VAD, with language-locked transcription."""
    speech = types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name=getattr(cfg, "DEFAULT_VOICE", "Aoede"),
            ),
        ),
    )
    decls = build_function_declarations(
        use_live_tools=cfg.LIVE_TOOLS_ENABLED,
        slim=getattr(cfg, "LIVE_TOOLS_SLIM", False),
    )
    tools = [types.Tool(function_declarations=decls)] if decls else []
    # Pro: language_code set karega taaki \"ある\" jaise Japanese mis-detect na ho
    try:
        lang_code = cfg.get_transcription_language_code(language)
    except Exception:
        lang_code = "hi-IN"
    try:
        in_trans = types.AudioTranscriptionConfig(language_codes=[lang_code])
    except Exception:
        in_trans = types.AudioTranscriptionConfig()
    try:
        out_trans = types.AudioTranscriptionConfig(language_codes=[lang_code])
    except Exception:
        out_trans = types.AudioTranscriptionConfig()
    return types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        system_instruction=types.Content(parts=[types.Part(text=system_prompt)]),
        speech_config=speech,
        tools=tools,
        input_audio_transcription=in_trans,
        output_audio_transcription=out_trans,
    )


class MuskuLiveSession:
    """Per-client Musku Gemini Live session."""

    def __init__(self, browser_ws: Any, api_key: str, system_prompt: str = None, uid: str = None):
        self._ws = browser_ws
        self._api_key = api_key
        self._uid = uid
        self._session = None
        from live.telemetry import TurnTelemetry
        self._telemetry = TurnTelemetry()
        self._closed = False
        self._logged_first_audio = False
        self._user_turn_buf = ""
        self._model_turn_buf = ""
        self._user_turn_closed = False
        self._loop = None
        self._system_prompt = system_prompt or cfg.get_live_system_prompt()
        self._greeted = False
        self._greeted_time = 0.0
        self._pending_greeting = None
        self._greet_on_connect = False
        # Echo suppression: last model output for self-talk filter
        self._last_model_text = ""
        self._last_model_time = 0.0
        from live.streak_praise import subscribe_streak
        subscribe_streak(self, lambda: self._session, lambda: self._loop)

    @staticmethod
    def _merge_transcript(existing: str, piece: str) -> str:
        """Streaming deltas ko jod ke poori line banao (UI replace karta hai)."""
        piece = (piece or "").strip()
        if not piece:
            return existing
        if not existing:
            return piece
        if piece == existing:
            return existing
        if existing in piece and len(piece) >= len(existing):
            return piece
        if piece in existing:
            return existing
        sep = "" if (existing[-1] in " \n" or piece[0] in ".,!?;:") else " "
        return existing + sep + piece

    def _reset_turn_buffers(self):
        self._user_turn_buf = ""
        self._model_turn_buf = ""
        self._user_turn_closed = False

    def _prepare_user_piece(self, txt: str) -> bool:
        """Nayi user utterance ka chunk prepare karo. Returns True agar piece
        naya turn shuru karta hai (buffer reset hua).

        Gemini Live transcription 'turn_complete' ke baad bhi aa sakta hai
        (SDK: independent of model turn). Isliye bas closed-flag se reset mat
        karo — agar naya chunk pehle ke buffer ka continuation/superset hai
        (late same-turn chunk) to merge rahega AUR closed=True hi rahega
        (taaki isi turn ke aur late chunks bhi merge hon aur naya unrelated
        chunk hi reset kare). Bilkul alag text ho to nayi turn samjho aur
        fresh shuru karo."""
        piece = (txt or "").strip()
        if not self._user_turn_closed:
            return False
        buf = self._user_turn_buf.strip()
        if not buf:
            self._user_turn_closed = False
            return False
        if piece in buf or buf in piece:
            return False
        self._user_turn_buf = ""
        self._user_turn_closed = False
        return True

    def _close_user_turn(self):
        """Turn complete par user turn final mark karo — buffer turant wipe
        mat karo. Gemini Live transcription 'turn_complete' ke baad bhi aa
        sakta hai, to agli aakhri transcription chunk bhi merge ho jaye —
        long sentence ka pura text bubble me dikhe, sirf aakhri word nahi."""
        self._user_turn_closed = True

    @property
    def active(self) -> bool:
        return self._session is not None and not self._closed

    async def run(self):
        if not _HAVE_GENAI:
            await self._send({"type": "error", "error": "google-genai SDK missing"})
            return
        if not self._api_key:
            await self._send({"type": "error", "error": "API key missing"})
            return

        client = genai.Client(api_key=self._api_key)
        # language-aware config: use uid's language so transcription matches profile language
        lang_for_cfg = "hinglish"
        try:
            if self._uid:
                from user_context import load_config as _load_cfg
                _uc = _load_cfg(self._uid)
                lang_for_cfg = _uc.get("language", "hinglish")
        except Exception:
            pass
        config = build_musku_connect_config(self._system_prompt, language=lang_for_cfg)
        model = getattr(cfg, "DEFAULT_MODEL", "gemini-3.1-flash-live-preview")

        await self._send({"type": "status", "status": "connecting_gemini"})

        try:
            async with client.aio.live.connect(model=model, config=config) as session:
                self._session = session
                self._loop = asyncio.get_running_loop()
                print(f"[Musku-Live] Gemini connected ({model})")
                await self._send({"type": "status", "status": "connected"})
                await self._send({"type": "status", "status": "gemini_ready"})

                # Flush any greeting queued before Gemini connected (e.g. /api/start)
                if self._greet_on_connect or self._pending_greeting is not None:
                    try:
                        # pending may be True from old queue (now None), handle bool
                        pend = self._pending_greeting
                        if pend is True:
                            pend = None
                        await self.send_greeting(pend, force=True)
                    except Exception as e:
                        logger.debug("pending greeting flush: %s", e)
                    finally:
                        self._greet_on_connect = False
                        self._pending_greeting = None
                # Auto-greeting disabled — desktop jaisa: greeting ONLY on START press, bar-bar nahi

                browser_task = asyncio.create_task(self._browser_loop())
                gemini_task = asyncio.create_task(self._gemini_loop())
                done, pending = await asyncio.wait(
                    [browser_task, gemini_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
                    try:
                        await t
                    except asyncio.CancelledError:
                        pass
        except Exception as e:
            logger.error("Musku Live session error: %s", e)
            await self._send({"type": "error", "error": str(e)})
        finally:
            self._closed = True
            self._session = None
            self._greeted = False
            self._greet_on_connect = False

    async def send_proactive_prompt(self, prompt: str):
        """Proactive utterance — break, water, silence check-in.

        gemini-3.1-flash-live-preview allows send_client_content ONLY for seeding
        initial history; mid-conversation text MUST use send_realtime_input.
        """
        if not self._session or not prompt:
            return
        await self._session.send_realtime_input(text=str(prompt))

    async def send_realtime_text(self, text: str):
        if not self._session or not text:
            return
        await self._session.send_realtime_input(text=str(text))

    async def send_greeting(self, script: str | None = None, force: bool = False):
        """START greeting — dedupe + queue until Gemini session ready."""
        _dbg_log(f"[GREETING] send_greeting called script={script!r} force={force} _greeted={self._greeted} has_session={bool(self._session)}")
        if self._greeted and not force:
            _dbg_log("[GREETING] blocked by dedupe")
            return
        if not self._session:
            _dbg_log(f"[GREETING] queued (no session) script={script!r}")
            self._pending_greeting = script
            return
        from personal_profile import build_start_greeting_prompt
        prompt = build_start_greeting_prompt(script)
        _dbg_log(f"[GREETING] sending to Gemini prompt={prompt[:120]!r} ...")
        self._greeted = True
        try:
            import time as _t
            self._greeted_time = _t.time()
        except Exception:
            pass
        try:
            await self.send_proactive_prompt(prompt)
            _dbg_log("[GREETING] send_realtime_input done")
        except Exception as e:
            _dbg_log(f"[GREETING] send failed: {e}")
            import traceback; traceback.print_exc()
            _dbg_log(traceback.format_exc())

    async def send_client_text(self, text: str):
        if not self._session or not text:
            return
        await self._session.send_realtime_input(text=str(text))

    async def update_system_prompt(self, prompt: str):
        """Language/persona update — existing connection par realtime instruction
        inject (no naya session/queue). Naya prompt reconnect par bhi use hoga."""
        if not prompt:
            return
        self._system_prompt = str(prompt)
        if not self._session:
            return
        try:
            await self._session.send_realtime_input(
                text=(
                    "[INTERNAL INSTRUCTION — user ki baat nahi hai, reply DENA "
                    "NAHI. Ab se isi system-prompt ke language/persona rules "
                    "follow karo.]\n" + str(prompt)
                )
            )
        except Exception:
            pass

    async def _browser_loop(self):
        try:
            async for raw in self._ws:
                await self._on_browser(raw)
        except Exception as e:
            logger.debug("Browser loop end: %s", e)

    async def _gemini_loop(self):
        try:
            async for msg in self._session.receive():
                await self._on_gemini(msg)
        except Exception as e:
            logger.debug("Gemini loop end: %s", e)

    async def _on_browser(self, raw):
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="ignore")
            msg = json.loads(raw)
        except Exception:
            return
        if not isinstance(msg, dict):
            return

        if msg.get("audio"):
            self._telemetry.mark("MIC_CAPTURE")
            pcm = base64.b64decode(str(msg["audio"]))
            pcm = _apply_mic_gain(pcm)
            from live.mic_meter import publish_pcm_meter
            publish_pcm_meter(bytes(pcm))
            blob = types.Blob(mime_type="audio/pcm;rate=16000", data=pcm)
            await self._session.send_realtime_input(audio=blob)
            self._telemetry.mark("WS_UPLOAD")
            return

        mtype = msg.get("type")
        if mtype == "video" and msg.get("video"):
            jpeg = base64.b64decode(str(msg["video"]))
            blob = types.Blob(mime_type="image/jpeg", data=jpeg)
            await self._session.send_realtime_input(video=blob)
            return

        # Defensive: accept both {type:"text",text:...} and legacy {text:...} (index.html fix sends type)
        if msg.get("text") and (mtype == "text" or mtype is None or mtype == ""):
            text = str(msg["text"]).strip()
            _dbg_log(f"[BROWSER] text received: {text[:150]!r}")
            if not text:
                return
            if "[INTERNAL - START GREETING" in text or "[INTERNAL — START GREETING" in text:
                _dbg_log(f"[BROWSER] START GREETING detected: {text!r}")
                from personal_profile import get_respectful_start_greeting
                m = re.search(r"START GREETING:\s*(.*?)]", text)
                script = m.group(1).strip() if (m and m.group(1).strip()) else get_respectful_start_greeting()
                _dbg_log(f"[BROWSER] parsed script={script!r} -> calling send_greeting")
                await self.send_greeting(script, force=True)
                return
            if "[INTERNAL SPEAK]" in text:
                m = re.search(r"\[INTERNAL SPEAK\]\s*(.*)", text, re.S)
                clean = m.group(1).strip() if m and m.group(1) else text.replace("[INTERNAL SPEAK]", "").strip()
                if clean:
                    await self.send_proactive_prompt(clean)
                return
            self._user_turn_buf = live_display_text(text)
            # User ne apna naam bataya ("mujhe X bulao" / "my name is X") to persist karo
            try:
                from persona.name_resolver import maybe_save_user_name
                maybe_save_user_name(text)
            except Exception:
                pass
            # Runtime persona switch ("dost ki tarah baat karo" / "formal mode")
            try:
                from user_context import (
                    detect_persona_mode, set_relationship_mode,
                    get_uid, load_config, PERSONA_SWITCH_REPLY,
                )
                mode = detect_persona_mode(text)
                if mode:
                    uid = get_uid()
                    set_relationship_mode(uid, mode)
                    uconf = load_config(uid)
                    from live.voice_config import get_live_system_prompt
                    new_prompt = get_live_system_prompt(
                        boss_name=uconf.get("user_name", "S2"),
                        language=uconf.get("language", "hinglish"),
                        relationship_mode=mode,
                        uid=self._uid,
                    )
                    await self.update_system_prompt(new_prompt)
                    await self.send_proactive_prompt(
                        "[INTERNAL — yeh user ki command hai, isse question mat samjho. "
                        "Bss natural awaaz se confirm karo.]\n" + PERSONA_SWITCH_REPLY[mode]
                    )
                    return
            except Exception:
                pass
            # Repeated hello/heylo — bar-bar same greeting ko playful tease karo, same generic hello repeat nahi
            try:
                import re as _re
                _low = text.lower()
                _hellos = _re.findall(r"\b(hello|heylo|helo|hey|hii|hi)\b", _low)
                _is_repeat_hello = len(_hellos) >= 3 or (len(_hellos) >= 2 and len(_low.split()) <= 5) or _low.strip() in ("heylo", "hello", "heylo heylo", "hello hello")
                # also check last 2 turns were hello
                if not _is_repeat_hello:
                    try:
                        from memory import turn_context as _tc
                        _snap = _tc.snapshot(self._uid)
                        _last_u = (_snap.get("last_user") or "").lower()
                        if _last_u and _re.search(r"\b(hello|heylo|hi)\b", _last_u) and _re.search(r"\b(hello|heylo|hi)\b", _low):
                            # consecutive hello
                            _is_repeat_hello = True
                    except Exception:
                        pass
                if _is_repeat_hello and "[INTERNAL" not in text:
                    # inject playful acknowledgement, brain will vary
                    text = text + " [INTERNAL HINT: user repeated hello playfully 3-4 times, don't just echo hello back. Tease cutely: 'arey heylo heylo, kya baat hai, itna pyaara hello!' vary each time, 1 short sentence, chulbul.]"
            except Exception:
                pass
            # Polite boundary — gali / abusive / nude (global deterministic, type= text)
            try:
                from persona.abuse_policy import is_abusive, get_polite_boundary_reply
                if "[INTERNAL" not in text and is_abusive(text):
                    reply_abuse = get_polite_boundary_reply(self._uid)
                    # user bubble already set, now model polite reply
                    self._model_turn_buf = live_display_text(reply_abuse)
                    await self._send({
                        "type": "transcription",
                        "role": "user",
                        "text": self._user_turn_buf,
                    })
                    await self._send({
                        "type": "transcription",
                        "role": "model",
                        "text": self._model_turn_buf,
                    })
                    # Voice me bhi Musku yehi bole
                    try:
                        await self.send_proactive_prompt(reply_abuse)
                    except Exception:
                        pass
                    # Deterministic turn save (no Gemini call for abusive input)
                    try:
                        import asyncio as _asyncio
                        _asyncio.create_task(self._persist_and_sync(self._user_turn_buf, reply_abuse))
                    except Exception:
                        pass
                    return
            except Exception:
                pass
            try:
                from monitoring.user_idle_checkin import get_user_idle_checkin
                eng = get_user_idle_checkin()
                if eng:
                    eng.on_user_speech(text)
            except Exception:
                pass
            await self._send({
                "type": "transcription",
                "role": "user",
                "text": self._user_turn_buf,
            })
            await self.send_client_text(text)
            return

        if mtype == "toolResponse" and msg.get("id"):
            fr = types.FunctionResponse(
                id=str(msg["id"]),
                name=str(msg.get("name") or "tool"),
                response={"output": msg.get("output") or {}},
            )
            await self._session.send_tool_response(function_responses=fr)

    async def _on_gemini(self, msg):
        # DEBUG: log every gemini message type — only when MUSKU_LIVE_DEBUG=1
        if _LIVE_DEBUG:
            try:
                has_sc = bool(getattr(msg, "server_content", None))
                has_tool = bool(getattr(msg, "tool_call", None))
                _dbg_log(f"[GEMINI] msg received has_sc={has_sc} has_tool={has_tool} msg={str(msg)[:500]!r}")
            except Exception:
                pass
        sc = getattr(msg, "server_content", None)
        if sc is not None:
            if getattr(sc, "interrupted", False):
                # Greeting ke pehle 3 sec me interrupted ignore — echo se greeting ka tail cut ho raha tha (good evening ke baad ruk jaana)
                try:
                    import time as _t
                    if self._greeted and (_t.time() - self._greeted_time) < 3.0:
                        _dbg_log("[INTERRUPTED] ignored during greeting grace (3s)")
                    else:
                        await self._send({"type": "interrupted"})
                        if self._model_turn_buf.strip():
                            try:
                                from memory import turn_context as _tctx
                                _tctx.record_last_musku_reply(self._model_turn_buf, uid=self._uid)
                            except Exception:
                                pass
                        self._model_turn_buf = ""
                except Exception:
                    await self._send({"type": "interrupted"})
                    self._model_turn_buf = ""

            mt = getattr(sc, "model_turn", None)
            if mt is not None and getattr(mt, "parts", None):
                for part in mt.parts:
                    inline = getattr(part, "inline_data", None)
                    if inline and getattr(inline, "data", None):
                        data = inline.data
                        if isinstance(data, str):
                            try:
                                data = base64.b64decode(data)
                            except Exception:
                                continue
                        if len(data) < 32:  # tiny keepalive, ignore
                            continue
                        # small tail (32-160) still play — was dropping greeting tail
                        if not self._logged_first_audio:
                            self._logged_first_audio = True
                            self._telemetry.mark("GEMINI_FIRST_AUDIO")
                            _live_dbg(f"[Musku-Live] First AI audio ({len(data)} bytes)")
                            bus.publish("AI_AUDIO_CHUNK", {"len": len(data), "queue": "muskuPlayPcm"})
                        try:
                            from monitoring.user_idle_checkin import get_user_idle_checkin
                            eng = get_user_idle_checkin()
                            if eng:
                                eng.on_musku_busy()
                        except Exception:
                            pass
                        b64 = base64.b64encode(bytes(data)).decode("ascii")
                        await self._send({"type": "audio", "audio": b64})

            user_txt = getattr(sc, "input_transcription", None)
            if user_txt is not None and getattr(user_txt, "text", None):
                is_finished = bool(getattr(user_txt, "finished", False))
                txt = live_display_text(str(user_txt.text))
                # Echo suppression: apne hi output ka speaker leak user me na aaye
                _is_echo = False
                try:
                    if txt.strip() and self._last_model_text:
                        import time as _t, difflib as _dl, re as _re
                        _now = _t.time()
                        # greeting echo window longer (greeting is long, tail may arrive late)
                        _win = 4.0 if self._greeted else 2.5
                        if _now - self._last_model_time < _win:
                            a = _re.sub(r"\s+", " ", txt.strip().lower())
                            b = _re.sub(r"\s+", " ", self._last_model_text.strip().lower())
                            if len(a) >= 8 and len(b) >= 8:
                                # greeting prefix echo: both start with "good morning/afternoon/evening"
                                if a.startswith("good ") and b.startswith("good "):
                                    # first 20 chars same -> definitely echo even if rest differs (maybe vs main bhi)
                                    if a[:20] == b[:20]:
                                        logger.debug("Echo drop (greeting prefix): user=%r model=%r", txt[:60], b[:60])
                                        _is_echo = True
                                    else:
                                        ratio = _dl.SequenceMatcher(None, a[:80], b[:80]).ratio()
                                        if ratio > 0.65:
                                            logger.debug("Echo drop (greeting %.2f): user=%r model=%r", ratio, txt[:60], b[:60])
                                            _is_echo = True
                                elif len(a) >= 10 and (a in b or b in a):
                                    logger.debug("Echo drop (substring long): user=%r model=%r", txt[:60], b[:60])
                                    _is_echo = True
                                else:
                                    # short hello/hi like "hello" (5 chars) in "arey hello hello..." should NOT be echo — real user turn
                                    if len(a) >= 8 and len(b) >= 8:
                                        ratio = _dl.SequenceMatcher(None, a, b).ratio()
                                        if ratio > 0.70:
                                            logger.debug("Echo drop (%.2f): user=%r model=%r", ratio, txt[:60], b[:60])
                                            _is_echo = True
                except Exception:
                    pass
                if _is_echo:
                    # drop this user transcription chunk only, model output still processed below
                    pass
                elif txt.strip():
                    self._prepare_user_piece(txt)
                    was_empty = not self._user_turn_buf.strip()
                    self._user_turn_buf = live_display_text(self._merge_transcript(self._user_turn_buf, txt))
                    if was_empty:
                        bus.publish("USER_SPEECH_PARTIAL", self._user_turn_buf)
                    try:
                        from monitoring.user_idle_checkin import get_user_idle_checkin
                        eng = get_user_idle_checkin()
                        if eng:
                            eng.on_user_speech(txt)
                    except Exception:
                        pass
                    _live_dbg(f"[Musku-Live] User: {self._user_turn_buf[:80]}")
                    await self._send({
                        "type": "transcription",
                        "role": "user",
                        "text": self._user_turn_buf,
                    })
                    if is_finished:
                        try:
                            from memory import turn_context as _tctx
                            _tctx.record_last_user_message(self._user_turn_buf, uid=self._uid)
                        except Exception:
                            pass
                        bus.publish("USER_SPEECH_FINAL", self._user_turn_buf)
                        # User ne apna naam bataya to persist karo (cross-session)
                        try:
                            from persona.name_resolver import maybe_save_user_name
                            maybe_save_user_name(self._user_turn_buf)
                        except Exception:
                            pass
            else:
                ut = getattr(sc, "user_turn", None)
                if ut is not None and getattr(ut, "parts", None):
                    for part in ut.parts:
                        t = getattr(part, "text", None)
                        if t:
                            from live.streak_praise import is_streak_note
                            if is_streak_note(str(t)):
                                continue
                            txt = live_display_text(str(t))
                            self._prepare_user_piece(txt)
                            was_empty = not self._user_turn_buf.strip()
                            self._user_turn_buf = self._merge_transcript(self._user_turn_buf, txt)
                            if was_empty:
                                bus.publish("USER_SPEECH_PARTIAL", self._user_turn_buf)
                            try:
                                from monitoring.user_idle_checkin import get_user_idle_checkin
                                eng = get_user_idle_checkin()
                                if eng:
                                    eng.on_user_speech(txt)
                            except Exception:
                                pass
                            _live_dbg(f"[Musku-Live] User: {self._user_turn_buf[:80]}")
                            await self._send({
                                "type": "transcription",
                                "role": "user",
                                "text": self._user_turn_buf,
                            })
                            bus.publish("USER_SPEECH_FINAL", self._user_turn_buf)
                            try:
                                from memory import turn_context as _tctx
                                _tctx.record_last_user_message(self._user_turn_buf)
                            except Exception:
                                pass
                            break

            out_txt = getattr(sc, "output_transcription", None)
            if out_txt is not None and getattr(out_txt, "text", None):
                txt = live_display_text(str(out_txt.text))
                if txt.strip():
                    from live.display_filter import filter_unnecessary_laughter
                    self._model_turn_buf = self._merge_transcript(self._model_turn_buf, txt)
                    out_display = filter_unnecessary_laughter(self._user_turn_buf, self._model_turn_buf)
                    # store for echo suppression
                    try:
                        import time as _t
                        self._last_model_text = out_display
                        self._last_model_time = _t.time()
                    except Exception:
                        pass
                    _live_dbg(f"[Musku-Live] Musku: {out_display[:80]}")
                    # Greeting: both bubble text + voice (was voice-only, now both as per requirement)
                    await self._send({
                        "type": "transcription",
                        "role": "model",
                        "text": out_display,
                    })
            elif mt is not None and getattr(mt, "parts", None):
                for part in mt.parts:
                    t = getattr(part, "text", None)
                    if t:
                        txt = live_display_text(str(t))
                        from live.display_filter import filter_unnecessary_laughter
                        self._model_turn_buf = self._merge_transcript(self._model_turn_buf, txt)
                        out_display = filter_unnecessary_laughter(self._user_turn_buf, self._model_turn_buf)
                        try:
                            import time as _t
                            self._last_model_text = out_display
                            self._last_model_time = _t.time()
                        except Exception:
                            pass
                        await self._send({
                            "type": "transcription",
                            "role": "model",
                            "text": out_display,
                        })
                        break

            if getattr(sc, "turn_complete", False):
                user = self._user_turn_buf.strip()
                reply = self._model_turn_buf.strip()
                if reply:
                    try:
                        from memory import turn_context as _tctx
                        _tctx.record_last_musku_reply(reply, uid=self._uid)
                    except Exception:
                        pass
                if reply:
                    user_to_save = user.strip() if user.strip() else "[START greeting]"
                    asyncio.create_task(self._persist_and_sync(user_to_save, reply))
                try:
                    from monitoring.user_idle_checkin import get_user_idle_checkin
                    eng = get_user_idle_checkin()
                    if eng:
                        eng.on_musku_idle()
                except Exception:
                    pass
                await self._send({"type": "turnComplete"})
                self._close_user_turn()
                self._model_turn_buf = ""
                # Non-blocking telemetry emit (no-op unless MUSKU_LIVE_TELEMETRY=1)
                try:
                    rep = self._telemetry.report()
                    if rep:
                        await self._send({"type": "debug_telemetry", "metrics": rep})
                except Exception:
                    pass
                self._telemetry.reset()
                bus.publish("TURN_COMPLETE", {})

        tc = getattr(msg, "tool_call", None)
        if tc is not None and getattr(tc, "function_calls", None):
            for fc in tc.function_calls:
                # Sequential: multiple calls ek saath (parallel) chali to race hoti
                # hai — jaise openWebsite + playYouTube dono naye YouTube tabs khol
                # dete (dono ko lagta koi tab nahi hai). Pehla khatam, phir agla.
                try:
                    await self._handle_tool(fc)
                except Exception:
                    logger.warning("Tool handler error", exc_info=True)

    async def _persist_and_sync(self, user: str, reply: str):
        """Turn save + deep memory consolidation + memory_sync broadcast."""
        try:
            updated = await asyncio.to_thread(self._persist_turn_and_consolidate, user, reply, self._uid)
            if updated:
                await self._send({"type": "memory_sync", "memories": updated})
        except Exception as e:
            logger.warning("Memory sync failed: %s", e)

    @staticmethod
    def _persist_turn_and_consolidate(user: str, reply: str, uid: str = None):
        # asyncio.to_thread drops the tenant ContextVar, so re-establish the
        # verified uid here — otherwise paths.* and memory writes would hit the
        # shared "owner" scope and leak across users.
        if uid:
            try:
                from tenant_ctx import set_uid
                set_uid(uid)
            except Exception:
                pass
        try:
            from brain.memory_bridge import save_chat_log, _consolidate_background
            save_chat_log(None, user, reply, consolidate=False, uid=uid)
            _consolidate_background(user, uid=uid)
            from memory import store as _mstore
            return _mstore.load_all()
        except Exception as e:
            logger.warning("Memory consolidate failed: %s", e)
            return None

    @staticmethod
    def _persist_turn(user: str, reply: str):
        try:
            from brain.memory_bridge import save_chat_log
            save_chat_log(None, user, reply)
            print(f"[Musku-Live] Chat saved ({len(user)}+{len(reply)} chars)")
        except Exception as e:
            logger.warning("Chat save failed: %s", e)

    async def _handle_tool(self, fc):
        name = getattr(fc, "name", "") or ""
        args = dict(getattr(fc, "args", None) or {})
        call_id = getattr(fc, "id", None)
        if not call_id:
            return
        try:
            from latency_telemetry import telemetry
            telemetry.on_tool_call(name)
        except Exception:
            pass
        print(f"[Musku-Live] Tool call: {name} {json.dumps(args, ensure_ascii=False)[:120]}")
        try:
            output = await asyncio.to_thread(
                self._execute_tool, name, args, self._user_turn_buf.strip()
            )
            fr = types.FunctionResponse(
                id=call_id,
                name=name,
                response={"output": output if isinstance(output, dict) else {"result": str(output)}},
            )
            sess = self._session
            if sess is None:
                return
            await sess.send_tool_response(function_responses=fr)
        except Exception as e:
            logger.warning("Tool %s failed: %s", name, e)
            fr = types.FunctionResponse(
                id=call_id,
                name=name,
                response={"output": {"result": f"Error: {e}"}},
            )
            try:
                sess = self._session
                if sess is None:
                    return
                await sess.send_tool_response(function_responses=fr)
            except Exception:
                pass
        try:
            from latency_telemetry import telemetry
            telemetry.on_tool_complete()
        except Exception:
            pass

    @staticmethod
    def _execute_tool(name: str, args: dict, user_text: str = "") -> dict:
        """Executes pure conversational tools (memory & web info search).
        Guaranteed to NEVER execute any OS, PC, browser, application, or system control.
        """
        if name == "saveMemory":
            from memory.store import save_memory, format_live_memory_card
            category = str(args.get("category") or "profile").strip()
            fact = re.sub(r"\s+", " ", str(args.get("fact") or args.get("text") or "")).strip()
            if not fact:
                return {"result": "Kya yaad rakhna hai? Fact batao.", "saved": False}
            ok = save_memory(category, fact, source="realtime-live")
            return {
                "result": "Yaad rakh liya boss." if ok else "Ye pehle se yaad hai.",
                "saved": ok,
                "memory_card": format_live_memory_card(),
            }

        resolved_intent, data = resolve_live_tool(name, args)
        if resolved_intent == "web_search":
            query = (data.get("query") or user_text or "").strip()
            if not query:
                return {"result": "Search query empty."}
            try:
                from brain.search import web_search
                res = web_search(query)
                return {"result": res or "Search results unavailable."}
            except Exception:
                return {"result": "Search unavailable."}

        # PC / image / code etc — professional upgrade note with per-user name (global fixed for all users)
        try:
            from persona.name_resolver import resolve_greeting_term
            from persona.identity_policy import get_upgrade_note
            g = resolve_greeting_term()
            return {"result": get_upgrade_note(g if g != "dear" else "")}
        except Exception:
            return {"result": "Jii, jab S2 Sir mujhe upgrade karenge to ye function add kar denge, main is baat ko note kar rahi hu. 🥰"}

    async def _send(self, obj: dict):
        try:
            await self._ws.send(json.dumps(obj))
        except Exception:
            pass
