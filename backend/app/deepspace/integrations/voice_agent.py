from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import numpy as np
from faster_whisper import WhisperModel
from kokoro_onnx import Kokoro
from livekit import rtc
from livekit.agents import (
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.plugins import silero

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice-agent")

# Paths to local models
STT_MODEL_PATH = "/app/models/stt/faster-whisper-tiny.en"
TTS_MODEL_PATH = "/app/models/tts/kokoro-v1.0.onnx"
VOICES_PATH    = "/app/models/tts/voices-v1.0.bin"

# Global wake session states
session_awake_states = {}  # room_name -> {"is_awake": bool, "last_active_time": float}
active_speech_tasks = {}  # room_name -> asyncio.Task
session_stt = {}  # room_name -> bool
session_tts = {}  # room_name -> bool
initial_prompts = {}  # room_name -> initial_prompt string bias

# Multiple wake names/variations for high robustness under various phonetic spelling differences
WAKE_WORDS = [
    # AverQel variations
    "averqel", "everqel", "aver kel", "ever kel", "averqul", "overkill", "averqul", "aver-kel", "averquel", "everquel",
    # Jarvis variations
    "jarvis", "jarves", "jarv",
    # General assistant names
    "hey system", "system", "assistant", "hey assistant", "aver", "qel"
]

def check_and_extract_wake_word(transcript: str) -> tuple[bool, str]:
    cleaned = transcript.lower().strip()
    # Remove leading common punctuation/fillers
    cleaned = re.sub(r'^[,\.\?\!\-\s]+', '', cleaned)

    # Check if starts with a wake word
    for wake_word in WAKE_WORDS:
        # Match as whole words at the start
        pattern = r'^' + re.escape(wake_word) + r'\b'
        if re.search(pattern, cleaned):
            # Remove the wake word and any leading punctuation/spaces
            remaining = re.sub(pattern, '', cleaned)
            remaining = re.sub(r'^[,\.\?\!\-\s]+', '', remaining).strip()
            return True, remaining

    # Also support general contains in the first 3 words (e.g. "hey, check AverQel")
    words = cleaned.split()
    if len(words) >= 1:
        first_few = " ".join(words[:3])
        for wake_word in WAKE_WORDS:
            if wake_word in first_few:
                # Remove everything up to and including the wake word
                idx = cleaned.find(wake_word)
                remaining = cleaned[idx + len(wake_word):]
                remaining = re.sub(r'^[,\.\?\!\-\s]+', '', remaining).strip()
                return True, remaining

    return False, cleaned


# Lazy-loaded singletons
_stt_model: WhisperModel | None = None
_tts_model: Kokoro | None = None
is_agent_speaking = False


def get_stt() -> WhisperModel:
    global _stt_model
    if _stt_model is None:
        logger.info("Loading Faster-Whisper STT model...")
        _stt_model = WhisperModel(STT_MODEL_PATH, device="cpu", compute_type="float32")
        logger.info("Faster-Whisper loaded.")
    return _stt_model


def get_tts() -> Kokoro:
    global _tts_model
    if _tts_model is None:
        logger.info("Loading Kokoro v1.0 TTS model...")
        _tts_model = Kokoro(TTS_MODEL_PATH, VOICES_PATH)
        logger.info("Kokoro v1.0 loaded.")
    return _tts_model


async def broadcast_state(
    room: rtc.Room,
    state: str,
    node_id: str | None = None,
    text: str | None = None,
) -> None:
    """Push state update to the frontend via WebRTC data channel."""
    import json
    payload_dict = {"state": state, "node_id": node_id}
    if text is not None:
        payload_dict["text"] = text
    payload = json.dumps(payload_dict).encode()
    try:
        await room.local_participant.publish_data(payload)
    except Exception as e:
        logger.error("Failed to broadcast state to room: %s", e)


async def synthesize_and_speak(
    text: str,
    audio_source: rtc.AudioSource,
    room: rtc.Room,
    node_id: str | None = None,
) -> None:
    """Convert text to speech and stream it to the room with high precision pacing."""
    global is_agent_speaking

    # Cancel previous active speech task for this room if any
    prev_task = active_speech_tasks.get(room.name)
    if prev_task and not prev_task.done() and prev_task != asyncio.current_task():
        logger.info("Interrupting previous active speech playback task...")
        prev_task.cancel()
        try:
            await prev_task
        except asyncio.CancelledError:
            pass

    current_task = asyncio.current_task()
    active_speech_tasks[room.name] = current_task
    is_agent_speaking = True

    try:
        logger.info("Synthesizing TTS for text: %r", text)
        await broadcast_state(room, "speaking", node_id, text=text)
        tts = get_tts()

        loop = asyncio.get_running_loop()
        samples, sample_rate = await loop.run_in_executor(
            None, lambda: tts.create(text, voice="af_sarah", speed=1.0, lang="en-us")
        )
        logger.info("TTS synthesis complete. samples_len=%d, sample_rate=%d", len(samples), sample_rate)

        # Convert float32 -> int16 PCM
        int16 = (samples * 32767).astype(np.int16)
        chunk_size = 960  # 40ms at 24 kHz
        frame_duration = 0.04  # 40ms in seconds

        # High-precision pacing implementation to prevent schedule drift and stuttering
        start_time = time.perf_counter()

        for idx, i in enumerate(range(0, len(int16), chunk_size)):
            chunk = int16[i : i + chunk_size]
            if len(chunk) < chunk_size:
                chunk = np.pad(chunk, (0, chunk_size - len(chunk)))
            frame = rtc.AudioFrame(
                data=chunk.tobytes(),
                sample_rate=24000,
                num_channels=1,
                samples_per_channel=chunk_size,
            )
            await audio_source.capture_frame(frame)

            # Align sleep time based on start_time reference to prevent timing drift
            expected_time = start_time + (idx + 1) * frame_duration
            sleep_time = expected_time - time.perf_counter()
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

        logger.info("Finished streaming TTS audio frames.")
    except asyncio.CancelledError:
        logger.info("Speech playback task cancelled (interrupted).")
        raise
    except Exception as e:
        logger.error("Error in synthesize_and_speak: %s", e, exc_info=True)
    finally:
        if active_speech_tasks.get(room.name) == current_task:
            active_speech_tasks.pop(room.name, None)

        async def reset_speaking_flag():
            await asyncio.sleep(0.1)
            global is_agent_speaking
            is_agent_speaking = False
            await broadcast_state(room, "listening")
        asyncio.create_task(reset_speaking_flag())


async def _generate_spoken_text(prompt_text: str) -> str:
    try:
        provider, model_name = get_resolved_chat_provider()
        if not provider:
            return ""
        from app.providers.services.types import ChatGenerateRequest
        req = ChatGenerateRequest(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a concise, helpful voice assistant. Output ONLY the raw spoken dialogue segment. No markdown, no quotes, no conversational preamble. Keep it under 15 words."},
                {"role": "user", "content": prompt_text}
            ],
            temperature=0.3,
            max_tokens=60,
            base_url=provider.base_url,
            api_key=provider.api_key,
            stream=False
        )
        full_text = ""
        async for token in provider.stream_generate(req):
            full_text += token
        full_text = full_text.strip().replace('"', '').replace("'", "")
        return full_text
    except Exception as e:
        logger.error("Error generating spoken text: %s", e)
        return ""


async def _handle_agentic_step(
    event_type: str,
    step_data: dict[str, Any],
    audio_source: rtc.AudioSource,
    room: rtc.Room
) -> None:
    prompt = ""
    if event_type == "agent_plan":
        plan_text = step_data.get("plan") or step_data.get("details") or ""
        if plan_text:
            prompt = f"The agent formed a new plan: '{plan_text}'. Generate an extremely brief (max 10 words) verbal status update for the user indicating what you are about to do. Do not use markdown. E.g., 'Planning to verify the database, sir.'"
    elif event_type == "tool_start":
        tool_name = step_data.get("tool") or step_data.get("tool_name") or ""
        description = step_data.get("description") or ""
        if tool_name:
            prompt = f"The agent is starting the tool '{tool_name}' with description '{description}'. Generate a brief (max 10 words) verbal status update indicating you are running it. Do not use markdown. E.g., 'Running a check on the file system, sir.'"
    elif event_type in ("tool_error", "error"):
        tool_name = step_data.get("tool") or ""
        error_text = step_data.get("error") or ""
        prompt = f"The agent encountered an error running '{tool_name}'. Error: '{error_text}'. Generate a brief (max 12 words) comforting verbal update indicating you will try another way. E.g., 'The database query failed, trying another way, sir.'"
    elif event_type in ("done", "mission_done"):
        content = step_data.get("content") or step_data.get("text") or ""
        prompt = f"The task is successfully completed. Final answer summary: '{content}'. Generate a brief (max 20 words) conversational completion notice indicating you are finished and asking them to review. E.g., 'I have finished all tasks, sir. Everything is running. Please review the results.'"

    if prompt:
        spoken_text = await _generate_spoken_text(prompt)
        if spoken_text:
            await synthesize_and_speak(spoken_text, audio_source, room, node_id="orchestrator")


async def entrypoint(ctx: JobContext) -> None:
    logger.info("Voice agent starting — connecting to room: %s", ctx.room.name)
    await ctx.connect()
    session_stt[ctx.room.name] = False
    session_tts[ctx.room.name] = False

    # Warm up models immediately on room connect
    try:
        get_stt()
        get_tts()
    except Exception as exc:
        logger.error("Failed to load speech models: %s", exc)

    # Create outbound audio track for TTS playback
    audio_source = rtc.AudioSource(24000, 1)  # Kokoro outputs 24 kHz mono
    out_track = rtc.LocalAudioTrack.create_audio_track("agent-voice", audio_source)
    await ctx.room.local_participant.publish_track(out_track)
    logger.info("TTS playback track published.")

    # High-quality VAD config: less sensitive to background static noise/hum, triggers only on real speech
    vad = silero.VAD.load(
        activation_threshold=0.45,    # Triggers on clear speech syllables
        deactivation_threshold=0.35,  # Faster deactivation cut-off
        min_speech_duration=0.18,     # Ignore short clicks/pops under 180ms
        min_silence_duration=0.8,     # Wait 800ms before finishing speech segment
    )

    def process_remote_track(track: rtc.Track, participant: rtc.RemoteParticipant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            if participant.identity == ctx.room.local_participant.identity:
                logger.info("Ignoring agent's own audio track: %s", participant.identity)
                return
            if participant.identity.startswith("agent-"):
                logger.info("Ignoring other agent's audio track: %s", participant.identity)
                return
            logger.info("Processing audio track for participant: %s", participant.identity)
            asyncio.create_task(
                _process_incoming_audio(track, participant, ctx.room, audio_source, vad)
            )

    @ctx.room.on("track_subscribed")
    def on_track(
        track: rtc.Track,
        pub: rtc.TrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        logger.info("Track subscribed event fired: %s from %s", track.sid, participant.identity)
        process_remote_track(track, participant)

    @ctx.room.on("data_received")
    def on_data_received(data_packet: rtc.DataPacket) -> None:
        import json
        try:
            payload = data_packet.data
            data = json.loads(payload.decode())

            if data.get("type") == "set-mode":
                stt_active = data.get("stt", False)
                tts_active = data.get("tts", False)

                prev_tts = session_tts.get(ctx.room.name, False)
                session_stt[ctx.room.name] = stt_active
                session_tts[ctx.room.name] = tts_active
                initial_prompts[ctx.room.name] = data.get("initial_prompt", "")

                logger.info("Voice session for %s updated: STT=%s, TTS=%s with prompt bias: %r",
                            ctx.room.name, stt_active, tts_active, initial_prompts[ctx.room.name])

                # Speak confirmation only if TTS (speaker) is newly turned on
                if tts_active and not prev_tts:
                    import random
                    greetings = [
                        "I am online.",
                        "Ready for service.",
                        "Voice system active.",
                        "TTS synthesis initialized."
                    ]
                    msg = random.choice(greetings)
                    asyncio.create_task(
                        synthesize_and_speak(msg, audio_source, ctx.room, node_id="orchestrator")
                    )
            elif data.get("type") == "agentic-step":
                if session_tts.get(ctx.room.name, False):
                    event_type = data.get("event")
                    step_data = data.get("data") or {}
                    logger.info("Received agentic step for %s: %s", ctx.room.name, event_type)
                    asyncio.create_task(
                        _handle_agentic_step(event_type, step_data, audio_source, ctx.room)
                    )
            elif data.get("type") == "test-tts":
                text_to_speak = data.get("text", "Hello, I am AverQel. Audio output is working perfectly.")
                logger.info("Received test-tts request: %r", text_to_speak)
                asyncio.create_task(
                    synthesize_and_speak(text_to_speak, audio_source, ctx.room, node_id="orchestrator")
                )
        except Exception as e:
            logger.error("Error processing data message: %s", e)

    # Process any pre-existing tracks that are already subscribed/active
    logger.info("Checking pre-existing room participants and tracks...")
    for _p_id, participant in ctx.room.remote_participants.items():
        if participant.identity.startswith("agent-"):
            logger.info("Ignoring pre-existing agent participant on join: %s", participant.identity)
            continue
        logger.info("Found remote participant on join: %s", participant.identity)
        for _pub_id, publication in participant.track_publications.items():
            if publication.track:
                logger.info("Processing pre-existing track: %s", publication.track.sid)
                process_remote_track(publication.track, participant)
            elif publication.subscribed:
                logger.info("Track %s is subscribed but publication.track is not populated yet", publication.sid)


def run_transcribe(model: WhisperModel, arr: np.ndarray, beam_size: int, initial_prompt: str | None = None) -> str:
    """Run transcription with custom segment filtering to block static noise loop hallucinations."""
    segments, _ = model.transcribe(
        arr,
        beam_size=beam_size,
        language="en",
        vad_filter=True,
        word_timestamps=False,
        initial_prompt=initial_prompt
    )

    valid_texts = []
    for s in segments:
        text = s.text.strip()

        # 1. Filter out Whisper silent/noisy loop hallucinations
        if s.no_speech_prob > 0.55:
            logger.info("Ignoring segment due to high no_speech_prob (%.3f): %r", s.no_speech_prob, text)
            continue
        if s.compression_ratio > 2.4:
            logger.info("Ignoring segment due to high compression_ratio (%.3f): %r", s.compression_ratio, text)
            continue
        if s.avg_logprob < -1.0:
            logger.info("Ignoring segment due to low avg_logprob (%.3f): %r", s.avg_logprob, text)
            continue

        # 2. Filter out known static boilerplate sentences
        cleaned = re.sub(r'[^\w\s]', '', text.lower()).strip()
        if cleaned in (
            "thank you for watching", "thank you", "thank you very much",
            "go next", "you", "transcribing", "watching", "subscribe",
            "he", "she", "it", "they", "we", "i", "you got it", "hospital"
        ) or not cleaned:
            logger.info("Ignoring known static boilerplate hallucination: %r", text)
            continue

        valid_texts.append(s.text)

    return " ".join(valid_texts).strip()


async def _transcribe_partial(samples: list[float], room: rtc.Room) -> None:
    try:
        arr = np.array(samples, dtype=np.float32)
        max_amp = np.max(np.abs(arr)) * 32768.0 if len(arr) > 0 else 0
        if max_amp < 1200:
            return  # skip partial transcription for static/noise

        model = get_stt()
        initial_prompt = initial_prompts.get(room.name)
        loop = asyncio.get_running_loop()
        transcript = await loop.run_in_executor(None, run_transcribe, model, arr, 1, initial_prompt)

        if transcript:
            logger.info("Partial Transcript (amp %.1f): %r", max_amp, transcript)
            await broadcast_state(room, "listening", text=transcript)
    except Exception as exc:
        logger.error("Error in _transcribe_partial: %s", exc)


async def _process_incoming_audio(
    track: rtc.Track,
    participant: rtc.RemoteParticipant,
    room: rtc.Room,
    audio_source: rtc.AudioSource,
    vad: silero.VAD,
) -> None:
    audio_stream = rtc.AudioStream(track)
    vad_stream = vad.stream()

    # Start a background task to pull VAD events from the stream
    async def vad_worker():
        global is_agent_speaking
        from livekit.agents.vad import VADEventType

        speech_samples = []
        last_transcribe_time = 0.0
        resampler = rtc.AudioResampler(48000, 16000, num_channels=1)

        async for ev in vad_stream:
            # Ignore user speech if STT (mic) is not active
            if not session_stt.get(room.name, False):
                speech_samples.clear()
                continue
            # Handle user barge-in first
            if ev.type == VADEventType.START_OF_SPEECH:
                speech_samples.clear()
                last_transcribe_time = asyncio.get_event_loop().time()
                await broadcast_state(room, "listening", text="...")
                logger.info("Speech detected.")

                prev_task = active_speech_tasks.get(room.name)
                if prev_task and not prev_task.done():
                    logger.info("User barge-in detected. Cancelling active speech task.")
                    prev_task.cancel()
                    is_agent_speaking = False
                continue

            if is_agent_speaking:
                speech_samples.clear()
                continue

            if ev.type != VADEventType.INFERENCE_DONE:
                logger.info("VAD Event: type=%s", ev.type)

            # Accumulate audio when speech is ongoing for partial transcription
            if getattr(ev, "speaking", False) and getattr(ev, "frames", None):
                for frame in ev.frames:
                    if frame.sample_rate != 48000:
                        resampler = rtc.AudioResampler(frame.sample_rate, 16000, num_channels=1)
                    resampled_frames = resampler.push(frame)
                    for r_frame in resampled_frames:
                        s = np.frombuffer(r_frame.data, dtype=np.int16).astype(np.float32) / 32768.0
                        speech_samples.extend(s.tolist())

                # Partial transcription every ~0.8 seconds
                current_time = asyncio.get_event_loop().time()
                if len(speech_samples) > 16000 * 0.5 and (current_time - last_transcribe_time > 0.8):
                    last_transcribe_time = current_time
                    asyncio.create_task(_transcribe_partial(list(speech_samples), room))

            elif ev.type == VADEventType.END_OF_SPEECH:
                # Add the remaining end of speech frames
                if getattr(ev, "frames", None):
                    for frame in ev.frames:
                        if frame.sample_rate != 48000:
                            resampler = rtc.AudioResampler(frame.sample_rate, 16000, num_channels=1)
                        resampled_frames = resampler.push(frame) + resampler.flush()
                        for r_frame in resampled_frames:
                            s = np.frombuffer(r_frame.data, dtype=np.int16).astype(np.float32) / 32768.0
                            speech_samples.extend(s.tolist())

                if speech_samples:
                    logger.info("Speech ended. Buffer size: %d samples", len(speech_samples))
                    await broadcast_state(room, "thinking")
                    asyncio.create_task(
                        _transcribe_and_respond(list(speech_samples), room, audio_source, participant)
                    )
                    speech_samples.clear()
                else:
                    logger.info("Speech ended but no samples accumulated.")
                    await broadcast_state(room, "listening")

    worker_task = asyncio.create_task(vad_worker())

    try:
        logger.info("Audio stream started for participant %s. Entering frame processing loop.", participant.identity)
        frame_count = 0
        async for event in audio_stream:
            audio_frame = event.frame
            frame_count += 1

            samples = np.frombuffer(audio_frame.data, dtype=np.int16)
            max_amp = np.max(np.abs(samples)) if len(samples) > 0 else 0

            if frame_count % 100 == 0:
                logger.info(
                    "Processed %d audio frames for participant %s. "
                    "Frame: rate=%d, channels=%d, samples=%d, bytes=%d, max_amp=%d",
                    frame_count,
                    participant.identity,
                    audio_frame.sample_rate,
                    audio_frame.num_channels,
                    audio_frame.samples_per_channel,
                    len(audio_frame.data),
                    max_amp
                )

            vad_stream.push_frame(audio_frame)
    finally:
        await vad_stream.aclose()
        worker_task.cancel()



def get_resolved_chat_provider():
    from sqlalchemy import select

    from app.platform.database.session import SessionLocal
    from app.auth.models.user import User
    from app.providers.services.registry import ProviderRegistry
    from app.providers.services.selection_service import ProviderSelectionService

    db = SessionLocal()
    try:
        # Find user sainibhaowal039@gmail.com
        stmt = select(User).where(User.email == "sainibhaowal039@gmail.com")
        user = db.execute(stmt).scalar_one_or_none()
        if not user:
            # Fall back to the first user
            stmt = select(User).order_by(User.created_at.desc())
            user = db.execute(stmt).scalars().first()

        if not user:
            logger.error("No user found in database for resolving ChatProvider.")
            return None, None

        selection_service = ProviderSelectionService(db, None)
        selection = selection_service.resolve_chat(
            tenant_id=user.tenant_id,
            actor_user_id=user.id
        )

        registry = ProviderRegistry(selection_service.settings)
        if selection.candidates:
            for candidate in selection.candidates:
                # connectivity check for local endpoints (LM Studio, Ollama etc.)
                if candidate.provider_type == "lmstudio" or (candidate.base_url and "localhost" in candidate.base_url):
                    import socket
                    from urllib.parse import urlparse
                    parsed = urlparse(candidate.base_url)
                    try:
                        host = "host.docker.internal" if parsed.hostname in ("localhost", "127.0.0.1") else parsed.hostname
                        port = parsed.port or 80
                        with socket.create_connection((host, port), timeout=0.3):
                            pass
                    except Exception:
                        logger.warning("Local provider candidate %s at %s is unreachable. Trying next candidate.", candidate.provider_type, candidate.base_url)
                        continue

                logger.info("Selected Chat Provider: %s, model: %s", candidate.provider_type, candidate.model_name)
                provider = registry.get_chat_provider_from_selection(candidate)
                return provider, candidate.model_name

        # If lmstudio candidate is unreachable, check other active provider configs in database
        from app.providers.models.provider_config import ProviderConfig
        stmt = select(ProviderConfig).where(
            ProviderConfig.enabled,
            ProviderConfig.supports_chat,
        )
        configs = db.execute(stmt).scalars().all()
        for config in configs:
            if config.provider_type == "opencode-zen" or config.provider_type == "openai":
                logger.info("Falling back to active provider config: %s", config.provider_type)
                provider = registry._bind_chat_provider(
                    config.provider_type,
                    base_url=config.api_base_url,
                    api_key=None,
                )
                return provider, config.default_chat_model

        # Fallback to direct default settings provider
        provider = registry.get_chat_provider()
        return provider, selection_service.settings.llm_model
    except Exception as e:
        logger.error("Error resolving chat provider: %s", e)
        return None, None
    finally:
        db.close()


async def _transcribe_and_respond(
    samples: list[float],
    room: rtc.Room,
    audio_source: rtc.AudioSource,
    participant: rtc.RemoteParticipant,
) -> None:
    try:
        arr = np.array(samples, dtype=np.float32)
        max_amp = np.max(np.abs(arr)) * 32768.0 if len(arr) > 0 else 0
        logger.info("Speech segment max amplitude: %.1f", max_amp)

        if max_amp < 1500:  # Gated at 1500 to keep low-amplitude background noise out of STT
            logger.info("Ignoring silent/noise speech segment (amplitude %.1f below 1500 gate)", max_amp)
            await broadcast_state(room, "listening")
            return

        model = get_stt()
        initial_prompt = initial_prompts.get(room.name)

        loop = asyncio.get_running_loop()
        transcript = await loop.run_in_executor(None, run_transcribe, model, arr, 5, initial_prompt)
        logger.info("Transcript (amp %.1f): %r", max_amp, transcript)

        if not transcript:
            await broadcast_state(room, "listening")
            return

        # Broadcast final transcript as dictation-result and reset listening state
        import json
        logger.info("Broadcasting dictation result: %r", transcript)
        await broadcast_state(room, "listening")
        payload = json.dumps({"type": "dictation-result", "text": transcript}).encode()
        await room.local_participant.publish_data(payload)
        return

    except Exception as exc:
        logger.error("Error in transcribe/respond: %s", exc)
        await broadcast_state(room, "listening")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
