from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import numpy as np
import pytest

from app.deepspace.integrations import voice_agent

pytestmark = pytest.mark.unit_no_db


class FakeWhisper:
    def __init__(self, segments):
        self.segments = segments
        self.options = None

    def transcribe(self, _audio, **options):
        self.options = options
        return iter(self.segments), SimpleNamespace(language="en", language_probability=1.0)


class FakeRoom:
    def __init__(self, name: str):
        self.name = name


def segment(text: str, *, no_speech: float = 0.01, compression: float = 1.1, logprob: float = -0.2):
    return SimpleNamespace(
        text=text,
        no_speech_prob=no_speech,
        compression_ratio=compression,
        avg_logprob=logprob,
    )


def test_run_transcribe_preserves_short_valid_speech_and_disables_repeat_conditioning():
    model = FakeWhisper([segment(" you "), segment("hospital")])

    transcript = voice_agent.run_transcribe(model, np.ones(16000, dtype=np.float32), 5)

    assert transcript == "you hospital"
    assert model.options["language"] == "en"
    assert model.options["beam_size"] == 5
    assert model.options["condition_on_previous_text"] is False


def test_run_transcribe_filters_low_confidence_noise_segments():
    model = FakeWhisper(
        [
            segment("clear words"),
            segment("noise", no_speech=0.9),
            segment("loop", compression=3.2),
            segment("uncertain", logprob=-1.2),
        ]
    )

    transcript = voice_agent.run_transcribe(model, np.ones(16000, dtype=np.float32), 5)

    assert transcript == "clear words"


def test_get_stt_falls_back_to_installed_base_model_if_small_model_is_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    loaded = []

    def fake_whisper_model(model_path, **options):
        model = SimpleNamespace(path=model_path, options=options)
        loaded.append(model)
        return model

    monkeypatch.setattr(voice_agent, "_stt_model", None)
    monkeypatch.setattr(voice_agent, "STT_MODEL_PATH", voice_agent.DEFAULT_STT_MODEL_PATH)
    monkeypatch.setattr(
        voice_agent.os.path, "isdir", lambda path: path == voice_agent.FALLBACK_STT_MODEL_PATH
    )
    monkeypatch.setattr(voice_agent, "WhisperModel", fake_whisper_model)

    model = voice_agent.get_stt()

    assert model.path == voice_agent.FALLBACK_STT_MODEL_PATH
    assert model.options == {"device": "cpu", "compute_type": "int8", "cpu_threads": 4}
    assert loaded == [model]


@pytest.mark.asyncio
async def test_partial_and_final_transcriptions_are_serialized_per_voice_room(
    monkeypatch: pytest.MonkeyPatch,
):
    room = FakeRoom("voice-transcription-lock")
    active_calls = 0
    maximum_active_calls = 0

    def slow_transcribe(*_args):
        nonlocal active_calls, maximum_active_calls
        active_calls += 1
        maximum_active_calls = max(maximum_active_calls, active_calls)
        time.sleep(0.02)
        active_calls -= 1
        return "recognized words"

    monkeypatch.setattr(voice_agent, "get_stt", lambda: object())
    monkeypatch.setattr(voice_agent, "run_transcribe", slow_transcribe)
    monkeypatch.setitem(voice_agent.initial_prompts, room.name, "")
    voice_agent.transcription_locks.pop(room.name, None)

    await asyncio.gather(
        voice_agent._transcribe_samples([0.1] * 16000, room, beam_size=5),
        voice_agent._transcribe_samples([0.1] * 16000, room, beam_size=5),
    )

    assert maximum_active_calls == 1


@pytest.mark.asyncio
async def test_partial_transcript_uses_low_latency_decode_and_carries_segment_id(
    monkeypatch: pytest.MonkeyPatch,
):
    room = FakeRoom("voice-transcription-partial")
    calls = []
    states = []

    def fake_transcribe(_model, _audio, beam_size, _prompt):
        calls.append(beam_size)
        return "current partial"

    async def fake_state(_room, state, **options):
        states.append((state, options))

    monkeypatch.setattr(voice_agent, "get_stt", lambda: object())
    monkeypatch.setattr(voice_agent, "run_transcribe", fake_transcribe)
    monkeypatch.setattr(voice_agent, "broadcast_state", fake_state)
    monkeypatch.setitem(voice_agent.session_stt, room.name, True)
    monkeypatch.setitem(voice_agent.initial_prompts, room.name, "")
    voice_agent.transcription_locks.pop(room.name, None)

    await voice_agent._transcribe_partial([0.1] * 16000, room, segment_id=5)

    assert calls == [1]
    assert states == [("listening", {"text": "current partial", "segment_id": 5})]


@pytest.mark.asyncio
async def test_final_transcript_is_sent_reliably_with_its_speech_segment_id(
    monkeypatch: pytest.MonkeyPatch,
):
    class FakeParticipant:
        def __init__(self):
            self.messages = []

        async def publish_data(self, payload, **options):
            self.messages.append((payload, options))

    class PublishRoom(FakeRoom):
        def __init__(self, name: str):
            super().__init__(name)
            self.local_participant = FakeParticipant()

    room = PublishRoom("voice-transcription-final")
    monkeypatch.setattr(voice_agent, "_transcribe_samples", _return_transcript)
    monkeypatch.setattr(voice_agent, "broadcast_state", _ignore_state)

    transcript = await voice_agent._transcribe_audio_segment([0.1] * 16000, room, segment_id=12)

    assert transcript == "final recognized phrase"
    assert len(room.local_participant.messages) == 1
    payload, options = room.local_participant.messages[0]
    import json

    assert json.loads(payload) == {
        "type": "dictation-result",
        "text": "final recognized phrase",
        "segment_id": 12,
    }
    assert options == {"reliable": True, "topic": "voice-control"}


@pytest.mark.asyncio
async def test_pause_flush_transcribes_and_clears_the_current_phrase(
    monkeypatch: pytest.MonkeyPatch,
):
    room = FakeRoom("voice-dictation-flush")
    samples = [0.1, 0.2, 0.3]
    calls = []

    async def fake_transcribe(audio, _room, segment_id):
        calls.append((audio, segment_id))
        return "phrase complete"

    states = []

    async def fake_state(_room, state, **options):
        states.append((state, options))

    monkeypatch.setattr(voice_agent, "_transcribe_audio_segment", fake_transcribe)
    monkeypatch.setattr(voice_agent, "broadcast_state", fake_state)

    result = await voice_agent._flush_dictation_buffer(samples, room, segment_id=7)

    assert result == "phrase complete"
    assert samples == []
    assert calls == [([0.1, 0.2, 0.3], 7)]
    assert states == [("thinking", {"segment_id": 7})]


def test_control_flush_keeps_resampler_tail_samples(monkeypatch: pytest.MonkeyPatch):
    class FakeAudioResampler:
        instances = []

        def __init__(self, *_args, **_kwargs):
            self.instances.append(self)

        def push(self, _frame):
            return []

        def flush(self):
            return [SimpleNamespace(data=np.array([16384], dtype=np.int16).tobytes())]

    monkeypatch.setattr(voice_agent.rtc, "AudioResampler", FakeAudioResampler)
    current_resampler = FakeAudioResampler(48000, 16000, num_channels=1)
    speech_samples = []

    next_resampler = voice_agent._append_audio_frames(
        [], current_resampler, speech_samples, flush=True
    )

    assert speech_samples == [0.5]
    assert next_resampler is not current_resampler
    assert len(FakeAudioResampler.instances) == 2


def test_vad_audio_collection_keeps_start_frames_without_duplicating_end_buffer(
    monkeypatch: pytest.MonkeyPatch,
):
    from livekit.agents.vad import VADEventType

    class FakeAudioResampler:
        def __init__(self, *_args, **_kwargs):
            pass

        def push(self, frame):
            return [frame]

        def flush(self):
            return []

    def frame(samples: list[int]):
        return SimpleNamespace(
            data=np.asarray(samples, dtype=np.int16).tobytes(),
            sample_rate=48000,
        )

    monkeypatch.setattr(voice_agent.rtc, "AudioResampler", FakeAudioResampler)
    resampler = FakeAudioResampler(48000, 16000, num_channels=1)
    speech_samples = []

    resampler = voice_agent._collect_vad_event_audio(
        SimpleNamespace(type=VADEventType.START_OF_SPEECH, frames=[frame([100, 200])]),
        VADEventType,
        resampler,
        speech_samples,
    )
    resampler = voice_agent._collect_vad_event_audio(
        SimpleNamespace(
            type=VADEventType.INFERENCE_DONE,
            speaking=True,
            frames=[frame([300, 400])],
        ),
        VADEventType,
        resampler,
        speech_samples,
    )
    voice_agent._collect_vad_event_audio(
        SimpleNamespace(
            type=VADEventType.END_OF_SPEECH,
            frames=[frame([100, 200, 300, 400])],
        ),
        VADEventType,
        resampler,
        speech_samples,
    )

    assert speech_samples == [100 / 32768, 200 / 32768, 300 / 32768, 400 / 32768]


@pytest.mark.asyncio
async def test_pause_acknowledgement_is_reliable_and_correlated_to_the_request():
    class FakeParticipant:
        def __init__(self):
            self.messages = []

        async def publish_data(self, payload, **options):
            self.messages.append((payload, options))

    class PublishRoom(FakeRoom):
        def __init__(self, name: str):
            super().__init__(name)
            self.local_participant = FakeParticipant()

    room = PublishRoom("voice-dictation-control-ack")
    await voice_agent._publish_dictation_control_result(room, "pause", "request-42")

    payload, options = room.local_participant.messages[0]
    import json

    assert json.loads(payload) == {
        "type": "dictation-control-result",
        "action": "pause",
        "request_id": "request-42",
    }
    assert options == {"reliable": True, "topic": "voice-control"}


@pytest.mark.asyncio
async def test_voice_mode_acknowledgement_echoes_mode_and_request_id():
    class FakeParticipant:
        def __init__(self):
            self.messages = []

        async def publish_data(self, payload, **options):
            self.messages.append((payload, options))

    class PublishRoom(FakeRoom):
        def __init__(self, name: str):
            super().__init__(name)
            self.local_participant = FakeParticipant()

    room = PublishRoom("voice-mode-ack")
    await voice_agent._publish_voice_mode_result(room, True, False, "mode-request-7")

    payload, options = room.local_participant.messages[0]
    import json

    assert json.loads(payload) == {
        "type": "voice-mode-result",
        "stt": True,
        "tts": False,
        "request_id": "mode-request-7",
        "ready": True,
    }
    assert options == {"reliable": True, "topic": "voice-control"}


@pytest.mark.asyncio
@pytest.mark.parametrize("fails,superseded", [(False, False), (True, False), (False, True)])
async def test_mode_waits_for_model_and_reports_readiness(monkeypatch, fails, superseded):
    import json
    import threading

    started = threading.Event()
    release = threading.Event()
    load_calls = 0

    def load_model():
        nonlocal load_calls
        load_calls += 1
        started.set()
        release.wait(2)
        if fails:
            raise RuntimeError("model unavailable")
        return object()

    class Participant:
        def __init__(self):
            self.messages = []

        async def publish_data(self, payload, **_options):
            self.messages.append(json.loads(payload))

        async def publish_track(self, _track):
            pass

    class Room(FakeRoom):
        def __init__(self):
            super().__init__("mode-readiness-test")
            self.local_participant = Participant()
            self.remote_participants = {}
            self.handlers = {}

        def on(self, event):
            def register(handler):
                self.handlers[event] = handler
                return handler

            return register

    room = Room()

    initial_payload = json.dumps(
        {"type": "set-mode", "stt": True, "tts": False, "request_id": "request"}
    ).encode()

    class Context:
        def add_shutdown_callback(self, callback):
            self.cleanup = callback

        async def connect(self):
            room.handlers["data_received"](SimpleNamespace(data=initial_payload))

    ctx = Context()
    ctx.room = room
    monkeypatch.setattr(voice_agent, "get_stt", load_model)
    monkeypatch.setattr(voice_agent.silero.VAD, "load", lambda **_kwargs: object())
    monkeypatch.setattr(
        voice_agent.rtc, "AudioSource", lambda *_args: SimpleNamespace(clear_queue=lambda: None)
    )
    monkeypatch.setattr(
        voice_agent.rtc.LocalAudioTrack, "create_audio_track", lambda *_args: object()
    )
    await voice_agent.entrypoint(ctx)
    try:
        assert await asyncio.to_thread(started.wait, 1)
        assert room.local_participant.messages == []
        room.handlers["data_received"](SimpleNamespace(data=initial_payload))
        await asyncio.sleep(0.05)
        assert load_calls == 1
        if superseded:
            payload = json.dumps(
                {"type": "set-mode", "stt": False, "tts": False, "request_id": "new"}
            ).encode()
            room.handlers["data_received"](SimpleNamespace(data=payload))
            for _ in range(100):
                if room.local_participant.messages:
                    break
                await asyncio.sleep(0.01)
        release.set()
        for _ in range(100):
            if room.local_participant.messages:
                break
            await asyncio.sleep(0.01)
        assert room.local_participant.messages[0]["ready"] is not fails
        if superseded:
            await asyncio.sleep(0.05)
            assert room.local_participant.messages[0]["request_id"] == "new"
            assert len(room.local_participant.messages) == 1
            assert voice_agent.session_stt[room.name] is False
        else:
            assert voice_agent.session_stt[room.name] is not fails
            room.handlers["data_received"](SimpleNamespace(data=initial_payload))
            for _ in range(100):
                if len(room.local_participant.messages) == 2:
                    break
                await asyncio.sleep(0.01)
            assert len(room.local_participant.messages) == 2
            assert load_calls == 1
    finally:
        release.set()
        await ctx.cleanup()


def test_prewarm_does_not_load_speech_models(monkeypatch):
    def forbidden():
        raise AssertionError("model loading blocks worker initialization")

    monkeypatch.setattr(voice_agent, "get_stt", forbidden)
    monkeypatch.setattr(voice_agent, "get_tts", forbidden)
    voice_agent.prewarm(SimpleNamespace(pid=123))


@pytest.mark.asyncio
async def test_tts_generation_does_not_block_event_loop_and_can_be_interrupted(monkeypatch):
    import threading

    started = threading.Event()
    release = threading.Event()

    class Model:
        def get_state_for_audio_prompt(self, _voice):
            return object()

        def generate_audio_stream(self, _state, _text):
            started.set()
            release.wait(2)
            yield np.ones(960, dtype=np.float32)

    class Source:
        async def capture_frame(self, _frame):
            raise AssertionError("interrupted speech must not play")

    room = FakeRoom("tts-interruption-test")
    monkeypatch.setattr(voice_agent, "get_tts", lambda: Model())
    monkeypatch.setattr(voice_agent, "broadcast_state", _ignore_state)
    task = asyncio.create_task(voice_agent.synthesize_and_speak("hello", Source(), room))
    try:
        assert await asyncio.to_thread(started.wait, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 0.5)
    finally:
        release.set()


async def _return_transcript(*_args, **_kwargs):
    return "final recognized phrase"


async def _ignore_state(*_args, **_kwargs):
    return None
