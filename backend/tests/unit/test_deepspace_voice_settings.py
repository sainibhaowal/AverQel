from __future__ import annotations

import asyncio
import io
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi import UploadFile

from app.auth.dependencies import AuthContext
from app.core.errors import ApiError
from app.deepspace.api import voice_settings
from app.deepspace.models.voice_settings import DeepSpaceVoiceSettings
from app.system.services.storage_service import StorageServiceError

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

    def get_state_for_audio_prompt(self, voice_name: str, **_kwargs) -> dict:
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
        payload=voice_settings.VoiceTestPayload(
            voice="cosette", speed=1.0, pitch=1.0, volume=1.0, text="Test speech"
        ),
        auth=auth,
        db=db,
    )

    assert response.status_code == 200
    assert response.media_type == "audio/wav"
    body = response.body
    assert body.startswith(b"RIFF")
    assert b"WAVE" in body


def test_test_voice_fallback_on_unavailable_voice(monkeypatch: pytest.MonkeyPatch) -> None:
    # An unavailable built-in voice state falls back to the supported default.
    fake_tts = FakeTTSModel(fail_voice="cosette")
    monkeypatch.setattr(voice_settings, "_get_tts_model", lambda: fake_tts)

    auth = _make_auth_context()
    db = MagicMock()

    response = voice_settings.test_voice(
        payload=voice_settings.VoiceTestPayload(voice="cosette"),
        auth=auth,
        db=db,
    )

    assert response.status_code == 200
    assert response.body.startswith(b"RIFF")


def test_test_voice_rejects_clone_from_another_tenant() -> None:
    auth = _make_auth_context()
    db = MagicMock()
    db.get.return_value = None

    with pytest.raises(ApiError) as exc_info:
        voice_settings.test_voice(
            payload=voice_settings.VoiceTestPayload(voice=f"clone:clone_{'a' * 32}"),
            auth=auth,
            db=db,
        )

    assert exc_info.value.code == "VOICE_CLONE_NOT_FOUND"
    assert exc_info.value.status_code == 404
    db.get.assert_called_once_with(DeepSpaceVoiceSettings, (auth.user_id, auth.tenant_id))


def test_test_voice_uses_only_an_owned_clone_file(monkeypatch: pytest.MonkeyPatch) -> None:
    auth = _make_auth_context()
    clone_id = f"clone_{'c' * 32}"
    storage_calls = []

    class FakeStorage:
        def __init__(self, _settings):
            pass

        def get_tenant_bytes(self, **kwargs):
            storage_calls.append(kwargs)
            return b"owned voice data"

    fake_tts = FakeTTSModel()
    monkeypatch.setattr(voice_settings, "StorageService", FakeStorage)
    monkeypatch.setattr(
        voice_settings, "get_settings", lambda: SimpleNamespace(minio_bucket="voice-bucket")
    )
    monkeypatch.setattr(voice_settings, "_get_tts_model", lambda: fake_tts)
    db = MagicMock()
    db.get.return_value = SimpleNamespace(cloned_voice_id=clone_id)

    response = voice_settings.test_voice(
        payload=voice_settings.VoiceTestPayload(voice=f"clone:{clone_id}"),
        auth=auth,
        db=db,
    )

    assert response.status_code == 200
    assert response.body.startswith(b"RIFF")
    assert storage_calls == [
        {
            "tenant_id": auth.tenant_id,
            "bucket": "voice-bucket",
            "object_key": f"{auth.tenant_id}/{auth.user_id}/{clone_id}.wav",
        }
    ]


def test_test_voice_error_raises_known_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenTTS:
        def get_state_for_audio_prompt(self, _v):
            raise RuntimeError("Fatal hardware failure")

    monkeypatch.setattr(voice_settings, "_get_tts_model", lambda: BrokenTTS())

    auth = _make_auth_context()
    db = MagicMock()

    with pytest.raises(ApiError) as exc_info:
        voice_settings.test_voice(
            payload=voice_settings.VoiceTestPayload(voice="alba"),
            auth=auth,
            db=db,
        )

    assert exc_info.value.code == "VOICE_TEST_FAILED"
    assert exc_info.value.status_code == 500
    assert "Fatal hardware failure" not in exc_info.value.message


def test_voice_settings_lookup_uses_user_and_tenant_identity() -> None:
    auth = _make_auth_context()
    db = MagicMock()
    row = SimpleNamespace(
        voice="alba",
        speed=1.0,
        pitch=1.0,
        volume=1.0,
        cloned_voice_id=None,
        cloned_voice_name=None,
    )
    db.get.return_value = row

    assert voice_settings._get_or_create(db, auth) is row
    db.get.assert_called_once_with(DeepSpaceVoiceSettings, (auth.user_id, auth.tenant_id))


def test_settings_cannot_select_a_clone_owned_by_another_row() -> None:
    auth = _make_auth_context()
    db = MagicMock()
    row = SimpleNamespace(cloned_voice_id=f"clone_{'b' * 32}")
    db.execute.return_value.scalar_one_or_none.return_value = row
    payload = voice_settings.VoiceSettingsPayload(
        voice=f"clone:clone_{'a' * 32}", clonedVoiceId=f"clone_{'a' * 32}"
    )

    with pytest.raises(ApiError) as exc_info:
        voice_settings.update_voice_settings(payload, auth=auth, db=db)

    assert exc_info.value.code == "VOICE_CLONE_NOT_FOUND"


def test_voice_test_rejects_unbounded_or_unknown_input() -> None:
    with pytest.raises(ValueError):
        voice_settings.VoiceTestPayload(text="   ")
    with pytest.raises(ValueError):
        voice_settings.VoiceTestPayload(text="x" * 401)
    with pytest.raises(ValueError):
        voice_settings.VoiceTestPayload(voice="../../other-user/voice")
    with pytest.raises(ValueError):
        voice_settings.VoiceSettingsPayload(speed=3.0)


def test_clone_upload_is_bounded_before_audio_processing() -> None:
    auth = _make_auth_context()
    db = MagicMock()
    audio = UploadFile(
        filename="sample.wav",
        file=io.BytesIO(b"x" * (voice_settings.MAX_CLONE_UPLOAD_BYTES + 1)),
    )

    with pytest.raises(ApiError) as exc_info:
        asyncio.run(voice_settings.clone_voice(audio=audio, name="Sample", auth=auth, db=db))

    assert exc_info.value.code == "VOICE_SAMPLE_TOO_LARGE"
    assert exc_info.value.status_code == 413
    db.get.assert_not_called()


def test_delete_cloned_voice_removes_owned_audio_before_clearing_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = _make_auth_context()
    clone_id = f"clone_{'d' * 32}"
    row = SimpleNamespace(
        cloned_voice_id=clone_id,
        cloned_voice_name="My voice",
        voice=f"clone:{clone_id}",
    )
    storage_calls = []

    class FakeStorage:
        def __init__(self, _settings):
            pass

        def delete_tenant_object(self, **kwargs):
            storage_calls.append(kwargs)

    monkeypatch.setattr(voice_settings, "StorageService", FakeStorage)
    monkeypatch.setattr(
        voice_settings, "get_settings", lambda: SimpleNamespace(minio_bucket="voice-bucket")
    )
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = row

    result = voice_settings.delete_cloned_voice(clone_id, auth=auth, db=db)

    assert result == {"status": "deleted"}
    assert row.cloned_voice_id is None
    assert row.cloned_voice_name is None
    assert row.voice == "alba"
    db.commit.assert_called_once()
    assert storage_calls == [
        {
            "tenant_id": auth.tenant_id,
            "bucket": "voice-bucket",
            "object_key": f"{auth.tenant_id}/{auth.user_id}/{clone_id}.wav",
            "raise_on_error": True,
        }
    ]


def test_delete_cloned_voice_keeps_settings_when_storage_delete_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = _make_auth_context()
    clone_id = f"clone_{'e' * 32}"
    row = SimpleNamespace(
        cloned_voice_id=clone_id,
        cloned_voice_name="My voice",
        voice=f"clone:{clone_id}",
    )

    class BrokenStorage:
        def __init__(self, _settings):
            pass

        def delete_tenant_object(self, **_kwargs):
            raise StorageServiceError(
                code="STORAGE_UNAVAILABLE",
                message="Unable to delete object.",
                retryable=True,
            )

    monkeypatch.setattr(voice_settings, "StorageService", BrokenStorage)
    monkeypatch.setattr(
        voice_settings, "get_settings", lambda: SimpleNamespace(minio_bucket="voice-bucket")
    )
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = row

    with pytest.raises(ApiError) as exc_info:
        voice_settings.delete_cloned_voice(clone_id, auth=auth, db=db)

    assert exc_info.value.code == "VOICE_STORAGE_UNAVAILABLE"
    assert exc_info.value.status_code == 503
    assert row.cloned_voice_id == clone_id
    assert row.cloned_voice_name == "My voice"
    assert row.voice == f"clone:{clone_id}"
    db.commit.assert_not_called()
