import asyncio

import pytest

from app.deepspace.integrations import voice_agent

pytestmark = pytest.mark.unit_no_db


class FakeRoom:
    def __init__(self, name: str) -> None:
        self.name = name


@pytest.mark.asyncio
async def test_voice_speech_queue_plays_chunks_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    room = FakeRoom("voice-speech-order")
    source = object()
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    second_started = asyncio.Event()
    spoken: list[str] = []

    async def fake_speak(text, _source, _room, node_id=None):
        spoken.append(text)
        if text == "First sentence.":
            first_started.set()
            await release_first.wait()
        else:
            second_started.set()

    async def ignore_state(*_args, **_kwargs):
        return None

    monkeypatch.setattr(voice_agent, "synthesize_and_speak", fake_speak)
    monkeypatch.setattr(voice_agent, "broadcast_state", ignore_state)
    monkeypatch.setitem(voice_agent.session_tts, room.name, True)

    voice_agent.enqueue_speech("First sentence.", source, room)
    voice_agent.enqueue_speech("Second sentence.", source, room)
    worker = voice_agent.speech_worker_tasks[room.name]

    await asyncio.wait_for(first_started.wait(), timeout=1)
    assert spoken == ["First sentence."]

    release_first.set()
    await asyncio.wait_for(second_started.wait(), timeout=1)
    await asyncio.wait_for(worker, timeout=1)

    assert spoken == ["First sentence.", "Second sentence."]


@pytest.mark.asyncio
async def test_voice_barge_in_cancels_playback_and_drops_queued_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    room = FakeRoom("voice-speech-barge-in")
    source = object()
    first_started = asyncio.Event()
    spoken: list[str] = []

    async def fake_speak(text, _source, _room, node_id=None):
        spoken.append(text)
        first_started.set()
        await asyncio.Event().wait()

    async def ignore_state(*_args, **_kwargs):
        return None

    monkeypatch.setattr(voice_agent, "synthesize_and_speak", fake_speak)
    monkeypatch.setattr(voice_agent, "broadcast_state", ignore_state)
    monkeypatch.setitem(voice_agent.session_tts, room.name, True)

    voice_agent.enqueue_speech("Current sentence.", source, room)
    voice_agent.enqueue_speech("This should not play.", source, room)
    await asyncio.wait_for(first_started.wait(), timeout=1)

    voice_agent.interrupt_speech(room)
    await asyncio.sleep(0)

    assert spoken == ["Current sentence."]
    assert voice_agent.session_speaking[room.name] is False
    assert not voice_agent.speech_queues[room.name]
