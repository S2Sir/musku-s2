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

_MIN_AI_PCM = 480
_LIVE_DEBUG = bool(getattr(cfg, "MUSKU_LIVE_DEBUG", False))


def _live_dbg(msg: str):
    if _LIVE_DEBUG:
        print(msg)


def build_musku_connect_config(system_prompt: str):
    """Musku Live connect — default VAD, no realtimeInputConfig."""
    speech = types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name=getattr(cfg, "DEFAULT_VOICE", "Aoede"),
            ),
        ),
    )
    tools = build_function_declarations(
        use_live_tools=cfg.LIVE_TOOLS_ENABLED,
        slim=getattr(cfg, "LIVE_TOOLS_SLIM", False),
    )
    return types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        system_instruction=types.Content(parts=[types.Part(text=system_prompt)]),
        speech_config=speech,
        tools=tools,
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )


class MuskuLiveSession:
    """Per-client Musku Gemini Live session."""

    def __init__(self, browser_ws: Any, api_key: str, system_prompt: str = None):
        self._ws = browser_ws
        self._api_key = api_key
        self._session = None
        self._closed = False
        self._logged_first_audio = False
        self._user_turn_buf = ""
        self._model_turn_buf = ""
        self._user_turn_closed = False
        self._loop = None
        self._system_prompt = system_prompt or cfg.get_live_system_prompt()
        self._greeted = False
        self._pending_greeting = None
        self._greet_on_connect = False
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
        config = build_musku_connect_config(self._system_prompt)
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
                        await self.send_greeting(self._pending_greeting)
                    except Exception as e:
                        logger.debug("pending greeting flush: %s", e)

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

    async def send_proactive_prompt(self, prompt: str):
        """Proactive utterance — break, water, silence check-in."""
        if not self._session or not prompt:
            return
        await self._session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=str(prompt))]),
            turn_complete=True,
        )

    async def send_realtime_text(self, text: str):
        if not self._session or not text:
            return
        await self._session.send_realtime_input(text=str(text))

    async def send_greeting(self, script: str | None = None):
        """START greeting — dedupe + queue until Gemini session ready.

        Dono source (/api/start server aur JS [INTERNAL - START GREETING]) isi
        method se jaate hain; `_greeted` double-greeting rokta hai. Session ready
        nahi hai toh queue karo, run() connect par flush karega."""
        if self._greeted:
            return
        if not self._session:
            self._pending_greeting = script
            return
        from personal_profile import build_start_greeting_prompt
        prompt = build_start_greeting_prompt(script)
        self._greeted = True
        await self.send_proactive_prompt(prompt)

    async def send_client_text(self, text: str):
        if not self._session or not text:
            return
        await self._session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=str(text))]),
            turn_complete=True,
        )

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
            pcm = base64.b64decode(str(msg["audio"]))
            pcm = _apply_mic_gain(pcm)
            from live.mic_meter import publish_pcm_meter
            publish_pcm_meter(bytes(pcm))
            blob = types.Blob(mime_type="audio/pcm;rate=16000", data=pcm)
            await self._session.send_realtime_input(audio=blob)
            return

        mtype = msg.get("type")
        if mtype == "video" and msg.get("video"):
            jpeg = base64.b64decode(str(msg["video"]))
            blob = types.Blob(mime_type="image/jpeg", data=jpeg)
            await self._session.send_realtime_input(video=blob)
            return

        if mtype == "text" and msg.get("text"):
            text = str(msg["text"]).strip()
            if not text:
                return
            if "[INTERNAL - START GREETING" in text or "[INTERNAL — START GREETING" in text:
                from personal_profile import get_respectful_start_greeting
                m = re.search(r"START GREETING:\s*(.*?)]", text)
                script = m.group(1).strip() if (m and m.group(1).strip()) else get_respectful_start_greeting()
                await self.send_greeting(script)
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
                    )
                    await self.update_system_prompt(new_prompt)
                    await self.send_proactive_prompt(
                        "[INTERNAL — yeh user ki command hai, isse question mat samjho. "
                        "Bss natural awaaz se confirm karo.]\n" + PERSONA_SWITCH_REPLY[mode]
                    )
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
        sc = getattr(msg, "server_content", None)
        if sc is not None:
            if getattr(sc, "interrupted", False):
                await self._send({"type": "interrupted"})
                if self._model_turn_buf.strip():
                    try:
                        from memory import turn_context as _tctx
                        _tctx.record_last_musku_reply(self._model_turn_buf)
                    except Exception:
                        pass
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
                        if len(data) < _MIN_AI_PCM:
                            continue
                        if not self._logged_first_audio:
                            self._logged_first_audio = True
                            _live_dbg(f"[Musku-Live] First AI audio ({len(data)} bytes)")
                            bus.publish("AI_AUDIO_CHUNK", {"len": len(data)})
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
                if txt.strip():
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
                    if is_finished:
                        try:
                            from memory import turn_context as _tctx
                            _tctx.record_last_user_message(self._user_turn_buf)
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
                    self._model_turn_buf = self._merge_transcript(self._model_turn_buf, txt)
                    _live_dbg(f"[Musku-Live] Musku: {self._model_turn_buf[:80]}")
                    await self._send({
                        "type": "transcription",
                        "role": "model",
                        "text": self._model_turn_buf,
                    })
            elif mt is not None and getattr(mt, "parts", None):
                for part in mt.parts:
                    t = getattr(part, "text", None)
                    if t:
                        txt = live_display_text(str(t))
                        self._model_turn_buf = self._merge_transcript(self._model_turn_buf, txt)
                        await self._send({
                            "type": "transcription",
                            "role": "model",
                            "text": self._model_turn_buf,
                        })
                        break

            if getattr(sc, "turn_complete", False):
                user = self._user_turn_buf.strip()
                reply = self._model_turn_buf.strip()
                if reply:
                    try:
                        from memory import turn_context as _tctx
                        _tctx.record_last_musku_reply(reply)
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
            updated = await asyncio.to_thread(self._persist_turn_and_consolidate, user, reply)
            if updated:
                await self._send({"type": "memory_sync", "memories": updated})
        except Exception as e:
            logger.warning("Memory sync failed: %s", e)

    @staticmethod
    def _persist_turn_and_consolidate(user: str, reply: str):
        try:
            from brain.memory_bridge import save_chat_log, _consolidate_background
            save_chat_log(None, user, reply, consolidate=False)
            _consolidate_background(user)
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

        # Any legacy tool call targeting PC control is politely refused conversationally
        return {"result": "Main aapka computer directly control nahi kar sakti, Boss. Main aapse baat karne aur aapke sawaalon ke jawab dene ke liye yahan hoon."}

    async def _send(self, obj: dict):
        try:
            await self._ws.send(json.dumps(obj))
        except Exception:
            pass
