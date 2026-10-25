from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections import deque

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
DEFAULT_STT_MODEL_PATH = "/app/models/stt/faster-whisper-small.en"
STT_MODEL_PATH = os.getenv("AVERQEL_STT_MODEL_PATH", DEFAULT_STT_MODEL_PATH)
FALLBACK_STT_MODEL_PATH = "/app/models/stt/faster-whisper-tiny.en"
TTS_MODEL_PATH = "/app/models/tts/kokoro-v1.0.onnx"
VOICES_PATH = "/app/models/tts/voices-v1.0.bin"

# Global wake session states
session_awake_states = {}  # room_name -> {"is_awake": bool, "last_active_time": float}
active_speech_tasks = {}  # room_name -> asyncio.Task
session_stt = {}  # room_name -> bool
session_tts = {}  # room_name -> bool
session_speaking = {}  # room_name -> bool
initial_prompts = {}  # room_name -> initial_prompt string bias
speech_queues: dict[str, deque[tuple[str, str | None]]] = {}
speech_worker_tasks: dict[str, asyncio.Task] = {}
dictation_control_queues: dict[str, asyncio.Queue[dict[str, str]]] = {}
transcription_locks: dict[str, asyncio.Lock] = {}

# Multiple wake names/variations for high robustness under various phonetic spelling differences
WAKE_WORDS = [
    # AverQel variations
    "averqel",
    "everqel",
    "aver kel",
    "ever kel",
    "averqul",
    "overkill",
    "averqul",
    "aver-kel",
    "averquel",
    "everquel",
    # Jarvis variations
    "jarvis",
    "jarves",
    "jarv",
    # General assistant names
    "hey system",
    "system",
    "assistant",
    "hey assistant",
    "aver",
    "qel",
]


def check_and_extract_wake_word(transcript: str) -> tuple[bool, str]:
    cleaned = transcript.lower().strip()
    # Remove leading common punctuation/fillers
    cleaned = re.sub(r"^[,\.\?\!\-\s]+", "", cleaned)

    # Check if starts with a wake word
    for wake_word in WAKE_WORDS:
        # Match as whole words at the start
        pattern = r"^" + re.escape(wake_word) + r"\b"
        if re.search(pattern, cleaned):
            # Remove the wake word and any leading punctuation/spaces
            remaining = re.sub(pattern, "", cleaned)
            remaining = re.sub(r"^[,\.\?\!\-\s]+", "", remaining).strip()
            return True, remaining

    # Also support general contains in the first 3 words (e.g. "hey, check AverQel")
    words = cleaned.split()
    if len(words) >= 1:
        first_few = " ".join(words[:3])
        for wake_word in WAKE_WORDS:
            if wake_word in first_few:
                # Remove everything up to and including the wake word
                idx = cleaned.find(wake_word)
                remaining = cleaned[idx + len(wake_word) :]
                remaining = re.sub(r"^[,\.\?\!\-\s]+", "", remaining).strip()
                return True, remaining

    return False, cleaned


# Lazy-loaded singletons
_stt_model: WhisperModel | None = None
_tts_model: Kokoro | None = None
TTS_VOICE = "am_michael"


def get_stt() -> WhisperModel:
    global _stt_model
    if _stt_model is None:
        model_path = STT_MODEL_PATH
        if (
            model_path == DEFAULT_STT_MODEL_PATH
            and not os.path.isdir(model_path)
            and os.path.isdir(FALLBACK_STT_MODEL_PATH)
        ):
            logger.warning(
                "Higher-accuracy STT model is missing; falling back to %s. Provision %s to enable the default model.",
                FALLBACK_STT_MODEL_PATH,
                DEFAULT_STT_MODEL_PATH,
            )
            model_path = FALLBACK_STT_MODEL_PATH
        logger.info("Loading Faster-Whisper STT model...")
        _stt_model = WhisperModel(
            model_path,
            device="cpu",
            compute_type="int8",
            cpu_threads=4,
        )
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
    segment_id: int | None = None,
) -> None:
    """Push state update to the frontend via WebRTC data channel."""
    import json

    payload_dict = {"state": state, "node_id": node_id}
    if text is not None:
        payload_dict["text"] = text
    if segment_id is not None:
        payload_dict["segment_id"] = segment_id
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
    session_speaking[room.name] = True

    try:
        logger.info("Synthesizing DeepSpace voice output (%d characters)", len(text))
        await broadcast_state(room, "speaking", node_id, text=text)
        tts = get_tts()

        loop = asyncio.get_running_loop()
        samples, sample_rate = await loop.run_in_executor(
            None, lambda: tts.create(text, voice=TTS_VOICE, speed=1.0, lang="en-us")
        )
        logger.info(
            "TTS synthesis complete. samples_len=%d, sample_rate=%d",
            len(samples),
            sample_rate,
        )

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
        logger.error("Error in DeepSpace voice synthesis: %s", e, exc_info=True)


def enqueue_speech(
    text: str,
    audio_source: rtc.AudioSource,
    room: rtc.Room,
    node_id: str | None = None,
) -> None:
    normalized_text = text.strip()
    if not normalized_text or len(normalized_text) > 320:
        return
    if not session_tts.get(room.name, False):
        return

    queue = speech_queues.setdefault(room.name, deque())
    if len(queue) >= 64:
        logger.warning("Dropping DeepSpace voice output because its room queue is full")
        return
    queue.append((normalized_text, node_id))

    worker = speech_worker_tasks.get(room.name)
    if worker is None or worker.done():
        worker = asyncio.create_task(_drain_speech_queue(room, audio_source))
        speech_worker_tasks[room.name] = worker
        active_speech_tasks[room.name] = worker


async def _drain_speech_queue(room: rtc.Room, audio_source: rtc.AudioSource) -> None:
    room_name = room.name
    current_task = asyncio.current_task()
    queue = speech_queues.setdefault(room_name, deque())
    try:
        while queue and session_tts.get(room_name, False):
            text, node_id = queue.popleft()
            await synthesize_and_speak(text, audio_source, room, node_id=node_id)
    except asyncio.CancelledError:
        logger.info("DeepSpace voice output interrupted for room %s", room_name)
        raise
    finally:
        if speech_worker_tasks.get(room_name) is current_task:
            speech_worker_tasks.pop(room_name, None)
            active_speech_tasks.pop(room_name, None)
            queue.clear()
            session_speaking[room_name] = False
            await broadcast_state(room, "listening")


def interrupt_speech(room: rtc.Room) -> None:
    room_name = room.name
    speech_queues.setdefault(room_name, deque()).clear()
    worker = speech_worker_tasks.get(room_name)
    if worker is not None and not worker.done():
        if speech_worker_tasks.get(room_name) is worker:
            speech_worker_tasks.pop(room_name, None)
        if active_speech_tasks.get(room_name) is worker:
            active_speech_tasks.pop(room_name, None)
        worker.cancel()
    session_speaking[room_name] = False


async def entrypoint(ctx: JobContext) -> None:
    logger.info("Voice agent starting — connecting to room: %s", ctx.room.name)
    await ctx.connect()
    session_stt[ctx.room.name] = False
    session_tts[ctx.room.name] = False
    session_speaking[ctx.room.name] = False
    dictation_control_queues[ctx.room.name] = asyncio.Queue()

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
        activation_threshold=0.45,  # Triggers on clear speech syllables
        deactivation_threshold=0.35,  # Faster deactivation cut-off
        min_speech_duration=0.18,  # Ignore short clicks/pops under 180ms
        min_silence_duration=0.8,  # Wait 800ms before finishing speech segment
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
            asyncio.create_task(_process_incoming_audio(track, participant, ctx.room, vad))

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

                logger.info(
                    "Voice session for %s updated: STT=%s, TTS=%s",
                    ctx.room.name,
                    stt_active,
                    tts_active,
                )
                request_id = data.get("request_id")
                if isinstance(request_id, str):
                    asyncio.create_task(
                        _publish_voice_mode_result(ctx.room, stt_active, tts_active, request_id)
                    )
                if prev_tts and not tts_active:
                    interrupt_speech(ctx.room)
            elif data.get("type") == "dictation-control":
                action = data.get("action")
                request_id = data.get("request_id")
                if action in {"pause", "finish"} and isinstance(request_id, str):
                    dictation_control_queues.setdefault(ctx.room.name, asyncio.Queue()).put_nowait(
                        {"action": action, "request_id": request_id}
                    )
            elif data.get("type") == "speak-text":
                text_to_speak = data.get("text")
                if isinstance(text_to_speak, str) and len(text_to_speak) <= 320:
                    enqueue_speech(text_to_speak, audio_source, ctx.room, node_id="deepspace")
        except Exception as e:
            logger.error("Error processing data message: %s", e)

    # Process any pre-existing tracks that are already subscribed/active
    logger.info("Checking pre-existing room participants and tracks...")
    for _p_id, participant in ctx.room.remote_participants.items():
        if participant.identity.startswith("agent-"):
            logger.info(
                "Ignoring pre-existing agent participant on join: %s",
                participant.identity,
            )
            continue
        logger.info("Found remote participant on join: %s", participant.identity)
        for _pub_id, publication in participant.track_publications.items():
            if publication.track:
                logger.info("Processing pre-existing track: %s", publication.track.sid)
                process_remote_track(publication.track, participant)
            elif publication.subscribed:
                logger.info(
                    "Track %s is subscribed but publication.track is not populated yet",
                    publication.sid,
                )


def run_transcribe(
    model: WhisperModel,
    arr: np.ndarray,
    beam_size: int,
    initial_prompt: str | None = None,
) -> str:
    """Run transcription with custom segment filtering to block static noise loop hallucinations."""
    segments, _ = model.transcribe(
        arr,
        beam_size=beam_size,
        language="en",
        vad_filter=True,
        word_timestamps=False,
        condition_on_previous_text=False,
        initial_prompt=initial_prompt,
    )

    valid_texts = []
    for s in segments:
        text = s.text.strip()

        # 1. Filter out Whisper silent/noisy loop hallucinations
        if s.no_speech_prob > 0.55:
            logger.info(
                "Ignoring speech segment due to high no_speech_prob (%.3f)",
                s.no_speech_prob,
            )
            continue
        if s.compression_ratio > 2.4:
            logger.info(
                "Ignoring speech segment due to high compression_ratio (%.3f)",
                s.compression_ratio,
            )
            continue
        if s.avg_logprob < -1.0:
            logger.info(
                "Ignoring speech segment due to low avg_logprob (%.3f)",
                s.avg_logprob,
            )
            continue

        # 2. Keep valid short answers; VAD and Whisper confidence scores handle noise.
        cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
        if not cleaned:
            logger.info("Ignoring empty transcription segment")
            continue

        valid_texts.append(text)

    return " ".join(valid_texts).strip()


async def _transcribe_samples(samples: list[float], room: rtc.Room, beam_size: int) -> str:
    lock = transcription_locks.setdefault(room.name, asyncio.Lock())
    async with lock:
        model = get_stt()
        initial_prompt = initial_prompts.get(room.name)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            run_transcribe,
            model,
            np.asarray(samples, dtype=np.float32),
            beam_size,
            initial_prompt,
        )


async def _transcribe_partial(samples: list[float], room: rtc.Room, segment_id: int) -> None:
    try:
        arr = np.array(samples, dtype=np.float32)
        max_amp = np.max(np.abs(arr)) * 32768.0 if len(arr) > 0 else 0
        if max_amp < 1200:
            return  # skip partial transcription for static/noise

        transcript = await _transcribe_samples(arr.tolist(), room, beam_size=1)

        if transcript and session_stt.get(room.name, False):
            logger.info("Partial transcription ready (%d characters)", len(transcript))
            await broadcast_state(room, "listening", text=transcript, segment_id=segment_id)
    except Exception as exc:
        logger.error("Error in _transcribe_partial: %s", exc)


async def _flush_dictation_buffer(samples: list[float], room: rtc.Room, segment_id: int) -> str:
    if not samples:
        return ""
    await broadcast_state(room, "thinking", segment_id=segment_id)
    transcript = await _transcribe_audio_segment(list(samples), room, segment_id)
    samples.clear()
    return transcript


async def _publish_dictation_control_result(room: rtc.Room, action: str, request_id: str) -> None:
    import json

    response = json.dumps(
        {
            "type": "dictation-control-result",
            "action": action,
            "request_id": request_id,
        }
    ).encode()
    await room.local_participant.publish_data(response, reliable=True, topic="voice-control")


async def _publish_voice_mode_result(
    room: rtc.Room, stt_active: bool, tts_active: bool, request_id: str
) -> None:
    import json

    response = json.dumps(
        {
            "type": "voice-mode-result",
            "stt": stt_active,
            "tts": tts_active,
            "request_id": request_id,
        }
    ).encode()
    try:
        await room.local_participant.publish_data(response, reliable=True, topic="voice-control")
    except Exception:
        logger.warning("Failed to acknowledge voice mode for room %s", room.name, exc_info=True)


def _append_audio_frames(frames, resampler, speech_samples: list[float], flush: bool = False):
    def append_resampled(resampled_frames) -> None:
        for resampled_frame in resampled_frames:
            samples = (
                np.frombuffer(resampled_frame.data, dtype=np.int16).astype(np.float32) / 32768.0
            )
            speech_samples.extend(samples.tolist())

    for frame in frames:
        if frame.sample_rate != 48000:
            resampler = rtc.AudioResampler(frame.sample_rate, 16000, num_channels=1)
        append_resampled(resampler.push(frame))
    if flush:
        append_resampled(resampler.flush())
        resampler = rtc.AudioResampler(48000, 16000, num_channels=1)
    return resampler


def _collect_vad_event_audio(ev, vad_event_type, resampler, speech_samples: list[float]):
    """Collect each VAD audio frame once, preserving the start-of-speech prefix."""
    if ev.type == vad_event_type.START_OF_SPEECH:
        speech_samples.clear()
        return _append_audio_frames(ev.frames, resampler, speech_samples)
    if ev.type == vad_event_type.INFERENCE_DONE and ev.speaking and ev.frames:
        return _append_audio_frames(ev.frames, resampler, speech_samples)
    if ev.type == vad_event_type.END_OF_SPEECH:
        # Silero's end event contains the whole buffered utterance. The audio
        # frames were already collected incrementally, so only drain resampler
        # latency here instead of appending the aggregate a second time.
        return _append_audio_frames((), resampler, speech_samples, flush=True)
    return resampler


async def _process_incoming_audio(
    track: rtc.Track,
    participant: rtc.RemoteParticipant,
    room: rtc.Room,
    vad: silero.VAD,
) -> None:
    audio_stream = rtc.AudioStream(track)
    vad_stream = vad.stream()

    # Consume speech and pause/finish commands in one task so a manual pause
    # can flush the current utterance without waiting for another VAD event.
    async def vad_worker():
        from livekit.agents.vad import VADEventType

        speech_samples = []
        last_transcribe_time = 0.0
        segment_id = 0
        partial_task: asyncio.Task | None = None
        resampler = rtc.AudioResampler(48000, 16000, num_channels=1)
        control_queue = dictation_control_queues.setdefault(room.name, asyncio.Queue())
        event_task = asyncio.create_task(vad_stream.__anext__())
        control_task = asyncio.create_task(control_queue.get())

        async def append_frames(frames, flush: bool = False) -> None:
            nonlocal resampler
            resampler = _append_audio_frames(frames, resampler, speech_samples, flush)

        async def process_vad_event(ev) -> None:
            nonlocal last_transcribe_time, segment_id, partial_task, resampler

            if not session_stt.get(room.name, False):
                speech_samples.clear()
                return
            if ev.type == VADEventType.START_OF_SPEECH:
                resampler = _collect_vad_event_audio(ev, VADEventType, resampler, speech_samples)
                segment_id += 1
                last_transcribe_time = asyncio.get_running_loop().time()
                await broadcast_state(room, "listening", text="...", segment_id=segment_id)
                logger.info("Speech detected.")

                if session_speaking.get(room.name, False):
                    logger.info("User barge-in detected. Cancelling active speech task.")
                    interrupt_speech(room)
                return

            if session_speaking.get(room.name, False):
                speech_samples.clear()
                return

            if ev.type != VADEventType.INFERENCE_DONE:
                logger.info("VAD Event: type=%s", ev.type)

            if getattr(ev, "speaking", False) and getattr(ev, "frames", None):
                resampler = _collect_vad_event_audio(ev, VADEventType, resampler, speech_samples)
                current_time = asyncio.get_running_loop().time()
                if len(speech_samples) > 16000 * 0.5 and current_time - last_transcribe_time > 1.0:
                    last_transcribe_time = current_time
                    if partial_task is None or partial_task.done():
                        partial_task = asyncio.create_task(
                            _transcribe_partial(list(speech_samples), room, segment_id)
                        )
                if not session_tts.get(room.name, False) and len(speech_samples) >= 16000 * 24:
                    if partial_task is not None:
                        await partial_task
                        partial_task = None
                    await _flush_dictation_buffer(speech_samples, room, segment_id)
                    segment_id += 1
                    await broadcast_state(room, "listening", text="...", segment_id=segment_id)
            elif ev.type == VADEventType.END_OF_SPEECH:
                resampler = _collect_vad_event_audio(ev, VADEventType, resampler, speech_samples)
                if speech_samples:
                    logger.info("Speech ended. Buffer size: %d samples", len(speech_samples))
                    if partial_task is not None:
                        await partial_task
                        partial_task = None
                    await _flush_dictation_buffer(speech_samples, room, segment_id)
                else:
                    logger.info("Speech ended but no samples accumulated.")
                    await broadcast_state(room, "listening")

        try:
            while True:
                done, _ = await asyncio.wait(
                    {event_task, control_task}, return_when=asyncio.FIRST_COMPLETED
                )

                # Include already-buffered VAD frames before honoring a control
                # command so pause/finish retains the last spoken syllables.
                if event_task in done:
                    try:
                        ev = event_task.result()
                    except StopAsyncIteration:
                        break
                    event_task = asyncio.create_task(vad_stream.__anext__())
                    await process_vad_event(ev)

                if control_task in done:
                    command = control_task.result()
                    control_task = asyncio.create_task(control_queue.get())
                    action = command["action"]
                    session_stt[room.name] = False
                    if partial_task is not None:
                        await partial_task
                        partial_task = None
                    await append_frames((), flush=True)
                    await _flush_dictation_buffer(speech_samples, room, segment_id)
                    await _publish_dictation_control_result(room, action, command["request_id"])
                    await broadcast_state(room, "idle")
        finally:
            for pending in (event_task, control_task):
                if not pending.done():
                    pending.cancel()
            await asyncio.gather(event_task, control_task, return_exceptions=True)

    worker_task = asyncio.create_task(vad_worker())

    try:
        logger.info(
            "Audio stream started for participant %s. Entering frame processing loop.",
            participant.identity,
        )
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
                    max_amp,
                )

            vad_stream.push_frame(audio_frame)
    finally:
        worker_task.cancel()
        await asyncio.gather(worker_task, return_exceptions=True)
        await vad_stream.aclose()


async def _transcribe_audio_segment(samples: list[float], room: rtc.Room, segment_id: int) -> str:
    try:
        arr = np.array(samples, dtype=np.float32)
        max_amp = np.max(np.abs(arr)) * 32768.0 if len(arr) > 0 else 0
        logger.info("Speech segment max amplitude: %.1f", max_amp)

        if max_amp < 1500:  # Gated at 1500 to keep low-amplitude background noise out of STT
            logger.info(
                "Ignoring silent/noise speech segment (amplitude %.1f below 1500 gate)",
                max_amp,
            )
            await broadcast_state(room, "listening")
            return ""

        transcript = await _transcribe_samples(arr.tolist(), room, beam_size=5)
        logger.info("Transcription completed (%d characters)", len(transcript))

        if not transcript:
            await broadcast_state(room, "listening")
            return ""

        # Broadcast final transcript as dictation-result and reset listening state
        import json

        logger.info("Sending a transcription result to the DeepSpace client")
        payload = json.dumps(
            {"type": "dictation-result", "text": transcript, "segment_id": segment_id}
        ).encode()
        await room.local_participant.publish_data(payload, reliable=True, topic="voice-control")
        await broadcast_state(room, "listening", segment_id=segment_id)
        return transcript

    except Exception as exc:
        logger.error("Error in transcribe/respond: %s", exc)
        await broadcast_state(room, "listening")
        return ""


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
