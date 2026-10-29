from __future__ import annotations

import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.auth.dependencies import AuthContext
from app.core.errors import ApiError
from app.deepspace.api import voice_settings

pytestmark = pytest.mark.unit_no_db


def _make_auth_context() -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        roles=frozenset(["admin"]),
        token_id="test-token",
        permissions=frozenset(["queries:run"]),
    )


class FakeTTSModel:
    def __init__(self, fail_voice: str | None = None) -> None:
        self.fail_voice = fail_voice

    def get_state_for_audio_prompt(self, voice_name: str) -> dict:
        if self.fail_voice and voice_name == self.fail_voice:
            raise RuntimeError(f"Voice {voice_name} not available")
        return {"voice": voice_name}

    def generate_audio_stream(self, voice_state: dict, text: str):
        # Yield 2 small chunks of synthetic int16 audio
        chunk1 = np.zeros(480, dtype=np.int16)
        chunk2 = np.ones(480, dtype=np.int16) * 1000
        yield chunk1
        yield chunk2


def test_tts_model_is_loaded_only_once_for_parallel_preview_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    calls_lock = threading.Lock()

    class FakeModel:
        pass

    class FakeTTS:
        @staticmethod
        def load_model():
            nonlocal calls
            with calls_lock:
                calls += 1
            time.sleep(0.02)
            return FakeModel()

    monkeypatch.setattr(voice_settings, "_tts_model", None)
    monkeypatch.setitem(sys.modules, "pocket_tts", SimpleNamespace(TTSModel=FakeTTS))

    with ThreadPoolExecutor(max_workers=8) as executor:
        models = list(executor.map(lambda _index: voice_settings._get_tts_model(), range(8)))

    assert calls == 1
    assert all(model is models[0] for model in models)


def test_tts_generation_is_serialized_for_parallel_preview_requests():
    active = 0
    max_active = 0
    lock = threading.Lock()

    class ConcurrentModel(FakeTTSModel):
        def generate_audio_stream(self, voice_state: dict, text: str):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            try:
                time.sleep(0.02)
                yield from super().generate_audio_stream(voice_state, text)
            finally:
                with lock:
                    active -= 1

    model = ConcurrentModel()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda text: voice_settings._generate_test_samples(model, "alba", text, None),
                ("first", "second"),
            )
        )

    assert max_active == 1
    assert all(len(samples) == 960 for samples in results)


def test_test_voice_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_tts = FakeTTSModel()
    monkeypatch.setattr(voice_settings, "_get_tts_model", lambda: fake_tts)

    auth = _make_auth_context()
    db = MagicMock()

    response = voice_settings.test_voice(
        payload={
            "voice": "cosette",
            "speed": 1.0,
            "pitch": 1.0,
            "volume": 1.0,
            "text": "Test speech",
        },
        auth=auth,
        db=db,
    )

    assert response.status_code == 200
    assert response.media_type == "audio/wav"
    body = response.body
    assert body.startswith(b"RIFF")
    assert b"WAVE" in body


def test_test_voice_fallback_on_unavailable_voice(monkeypatch: pytest.MonkeyPatch) -> None:
    # Voice 'missing_voice' fails, but fallback to 'alba' succeeds
    fake_tts = FakeTTSModel(fail_voice="missing_voice")
    monkeypatch.setattr(voice_settings, "_get_tts_model", lambda: fake_tts)

    auth = _make_auth_context()
    db = MagicMock()

    response = voice_settings.test_voice(
        payload={"voice": "missing_voice", "speed": 1.0, "pitch": 1.0, "volume": 1.0},
        auth=auth,
        db=db,
    )

    assert response.status_code == 200
    assert response.body.startswith(b"RIFF")


def test_test_voice_cloned_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_tts = FakeTTSModel()
    monkeypatch.setattr(voice_settings, "_get_tts_model", lambda: fake_tts)

    auth = _make_auth_context()
    db = MagicMock()
    # No clone row in db
    db.get.return_value = None

    response = voice_settings.test_voice(
        payload={"voice": "clone:nonexistent_clone_id", "speed": 1.2, "pitch": 1.0, "volume": 0.8},
        auth=auth,
        db=db,
    )

    assert response.status_code == 200
    assert response.body.startswith(b"RIFF")


def test_test_voice_error_raises_known_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenTTS:
        def get_state_for_audio_prompt(self, _v):
            raise RuntimeError("Fatal hardware failure")

    monkeypatch.setattr(voice_settings, "_get_tts_model", lambda: BrokenTTS())

    auth = _make_auth_context()
    db = MagicMock()

    with pytest.raises(ApiError) as exc_info:
        voice_settings.test_voice(
            payload={"voice": "alba"},
            auth=auth,
            db=db,
        )

    assert exc_info.value.code == "VOICE_TEST_FAILED"
    assert exc_info.value.status_code == 500
