"""Voice Studio settings API for DeepSpace."""

from __future__ import annotations

import io
import logging
import os
import re
import struct
import tempfile
import threading
import uuid
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.core.config import get_settings
from app.core.errors import ApiError
from app.deepspace.models.voice_settings import DeepSpaceVoiceSettings
from app.deepspace.voice_catalog import BUILT_IN_VOICES
from app.platform.database.session import get_db
from app.system.services.storage_service import StorageService, StorageServiceError

logger = logging.getLogger("deepspace-voice-settings")

router = APIRouter(prefix="/deepspace/voice", tags=["deepspace-voice"])

MAX_CLONE_UPLOAD_BYTES = 10 * 1024 * 1024
MIN_CLONE_DURATION_SECONDS = 1.0
MAX_CLONE_DURATION_SECONDS = 30.0
CLONE_ID_PATTERN = r"clone_[0-9a-f]{32}"
VOICE_PATTERN = rf"^(?:{'|'.join(sorted(BUILT_IN_VOICES))}|clone:{CLONE_ID_PATTERN})$"

# Global model cache
_tts_model = None
_tts_model_lock = threading.Lock()
_tts_generation_lock = threading.Lock()


def _get_tts_model() -> Any:
    global _tts_model
    if _tts_model is None:
        with _tts_model_lock:
            if _tts_model is None:
                import torch
                from pocket_tts import TTSModel

                try:
                    torch.set_num_threads(min(4, max(2, os.cpu_count() or 2)))
                    torch.set_num_interop_threads(1)
                except Exception:
                    pass
                _tts_model = TTSModel.load_model()
    return _tts_model


def _generate_test_samples(tts: Any, voice: str, text: str, clone_path: str | None) -> np.ndarray:
    """Serialize Pocket TTS access because its model state is not thread-safe."""
    with _tts_generation_lock:
        if voice.startswith("clone:"):
            if clone_path and os.path.exists(clone_path):
                voice_state = tts.get_state_for_audio_prompt(clone_path, truncate=True)
            else:
                raise ValueError("The selected cloned voice is unavailable")
        else:
            voice_name = voice.split(":")[-1] if ":" in voice else voice
            try:
                voice_state = tts.get_state_for_audio_prompt(voice_name)
            except Exception as voice_err:
                logger.warning(
                    "Failed to load voice %s (%s); falling back to alba",
                    voice_name,
                    voice_err,
                )
                voice_state = tts.get_state_for_audio_prompt("alba")

        chunks = []
        for audio_chunk in tts.generate_audio_stream(voice_state, text):
            samples = (
                audio_chunk.detach().cpu().numpy()
                if hasattr(audio_chunk, "detach")
                else np.asarray(audio_chunk)
            )
            if samples.dtype != np.int16:
                samples = (samples * 32767).astype(np.int16)
            chunks.append(samples)
        if not chunks:
            raise ValueError("No audio generated")
        return np.concatenate(chunks)


class VoiceSettingsPayload(BaseModel):
    voice: str = Field(default="alba", pattern=VOICE_PATTERN)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    pitch: float = Field(default=1.0, ge=0.5, le=2.0)
    volume: float = Field(default=1.0, ge=0.0, le=1.0)
    clonedVoiceId: str | None = Field(default=None, pattern=rf"^{CLONE_ID_PATTERN}$")  # noqa: N815
    clonedVoiceName: str | None = Field(default=None, max_length=64)  # noqa: N815


class VoiceTestPayload(BaseModel):
    voice: str = Field(default="alba", pattern=VOICE_PATTERN)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    pitch: float = Field(default=1.0, ge=0.5, le=2.0)
    volume: float = Field(default=1.0, ge=0.0, le=1.0)
    text: str = Field(default="Hello! How does this voice sound?", min_length=1, max_length=400)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be blank")
        return value


def _get_settings_row(
    db: Session, auth: AuthContext, *, for_update: bool = False
) -> DeepSpaceVoiceSettings | None:
    if not for_update:
        return db.get(DeepSpaceVoiceSettings, (auth.user_id, auth.tenant_id))
    statement = (
        select(DeepSpaceVoiceSettings)
        .where(
            DeepSpaceVoiceSettings.user_id == auth.user_id,
            DeepSpaceVoiceSettings.tenant_id == auth.tenant_id,
        )
        .with_for_update()
    )
    return db.execute(statement).scalar_one_or_none()


def _get_or_create(
    db: Session, auth: AuthContext, *, for_update: bool = False
) -> DeepSpaceVoiceSettings:
    row = _get_settings_row(db, auth, for_update=for_update)
    if row is None:
        row = DeepSpaceVoiceSettings(
            user_id=auth.user_id,
            tenant_id=auth.tenant_id,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _clone_object_key(auth: AuthContext, clone_id: str) -> str:
    if not re.fullmatch(CLONE_ID_PATTERN, clone_id):
        raise ApiError(
            code="VOICE_CLONE_NOT_FOUND",
            message="The selected cloned voice was not found.",
            status_code=404,
        )

    return f"{auth.tenant_id}/{auth.user_id}/{clone_id}.wav"


def _get_owned_clone_bytes(db: Session, auth: AuthContext, clone_id: str) -> bytes:
    row = db.get(DeepSpaceVoiceSettings, (auth.user_id, auth.tenant_id))
    if row is None or row.cloned_voice_id != clone_id:
        raise ApiError(
            code="VOICE_CLONE_NOT_FOUND",
            message="The selected cloned voice was not found.",
            status_code=404,
        )
    try:
        settings = get_settings()
        return StorageService(settings).get_tenant_bytes(
            tenant_id=auth.tenant_id,
            bucket=settings.minio_bucket,
            object_key=_clone_object_key(auth, clone_id),
        )
    except StorageServiceError as exc:
        if exc.code == "STORAGE_OBJECT_NOT_FOUND":
            raise ApiError(
                code="VOICE_CLONE_NOT_FOUND",
                message="The selected cloned voice was not found.",
                status_code=404,
            ) from exc
        raise ApiError(
            code="VOICE_STORAGE_UNAVAILABLE",
            message="Voice storage is temporarily unavailable.",
            status_code=503,
        ) from exc


def _row_to_dict(row: DeepSpaceVoiceSettings) -> dict[str, Any]:
    return {
        "voice": row.voice,
        "speed": row.speed,
        "pitch": row.pitch,
        "volume": row.volume,
        "clonedVoiceId": row.cloned_voice_id,
        "clonedVoiceName": row.cloned_voice_name,
    }


@router.get(
    "/settings",
    dependencies=[Depends(require_permissions("queries:run"))],
)
def get_voice_settings(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = _get_or_create(db, auth)
    return _row_to_dict(row)


@router.put(
    "/settings",
    dependencies=[Depends(require_permissions("queries:run"))],
)
def update_voice_settings(
    payload: VoiceSettingsPayload,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = _get_or_create(db, auth, for_update=True)
    if payload.clonedVoiceId is not None and row.cloned_voice_id != payload.clonedVoiceId:
        raise ApiError(
            code="VOICE_CLONE_NOT_FOUND",
            message="The selected cloned voice was not found.",
            status_code=404,
        )
    if payload.voice.startswith("clone:"):
        clone_id = payload.voice.split(":", 1)[1]
        if row.cloned_voice_id != clone_id:
            raise ApiError(
                code="VOICE_CLONE_NOT_FOUND",
                message="The selected cloned voice was not found.",
                status_code=404,
            )
    row.voice = payload.voice
    row.speed = payload.speed
    row.pitch = payload.pitch
    row.volume = payload.volume
    if payload.clonedVoiceId is not None:
        row.cloned_voice_id = payload.clonedVoiceId
        row.cloned_voice_name = payload.clonedVoiceName or row.cloned_voice_name
    db.commit()
    db.refresh(row)
    return _row_to_dict(row)


@router.post(
    "/test",
    dependencies=[Depends(require_permissions("queries:run"))],
)
def test_voice(
    payload: VoiceTestPayload,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Any:
    text = payload.text
    voice = payload.voice
    speed = payload.speed
    # Keep accepting pitch for saved-settings compatibility; Pocket TTS does not
    # currently provide pitch shifting, so the UI states that this is unsupported.
    volume = payload.volume

    clone_path = None
    clone_content = None
    if voice.startswith("clone:"):
        clone_id = voice.split(":", 1)[1]
        clone_content = _get_owned_clone_bytes(db, auth, clone_id)

    try:
        tts = _get_tts_model()
        if clone_content is not None:
            with tempfile.NamedTemporaryFile(prefix="averqel-voice-", suffix=".wav") as sample_file:
                sample_file.write(clone_content)
                sample_file.flush()
                clone_path = sample_file.name
                all_audio = _generate_test_samples(tts, voice, text, clone_path)
        else:
            all_audio = _generate_test_samples(tts, voice, text, clone_path)

        # Apply speed (simple resampling)
        if speed != 1.0 and speed > 0:
            new_len = int(len(all_audio) / speed)
            indices = np.linspace(0, len(all_audio) - 1, new_len).astype(int)
            all_audio = all_audio[indices]

        # Apply volume
        if volume != 1.0:
            all_audio = np.clip(all_audio * volume, -32768, 32767).astype(np.int16)

        # Convert to WAV
        sample_rate = 24000
        buf = io.BytesIO()
        data_size = len(all_audio) * 2
        buf.write(b"RIFF")
        buf.write(struct.pack("<I", 36 + data_size))
        buf.write(b"WAVE")
        buf.write(b"fmt ")
        buf.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
        buf.write(b"data")
        buf.write(struct.pack("<I", data_size))
        buf.write(all_audio.astype(np.int16).tobytes())
        buf.seek(0)

        return Response(content=buf.read(), media_type="audio/wav")
    except ApiError:
        raise
    except Exception as e:
        logger.error("Voice test failed: %s", e, exc_info=True)
        raise ApiError(
            code="VOICE_TEST_FAILED",
            message="Voice preview could not be generated.",
            status_code=500,
        ) from e


@router.post(
    "/clone",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def clone_voice(
    audio: UploadFile = File(...),  # noqa: B008
    name: str = Form("Cloned Voice"),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    import soundfile as sf

    name = name.strip()
    if not name or len(name) > 64:
        raise ApiError(
            code="INVALID_VOICE_NAME",
            message="Voice name must contain between 1 and 64 characters.",
            status_code=422,
        )

    content = await audio.read(MAX_CLONE_UPLOAD_BYTES + 1)
    if len(content) > MAX_CLONE_UPLOAD_BYTES:
        raise ApiError(
            code="VOICE_SAMPLE_TOO_LARGE",
            message="Voice samples must be 10 MB or smaller.",
            status_code=413,
        )
    if not content:
        raise ApiError(
            code="INVALID_VOICE_SAMPLE",
            message="Choose a non-empty WAV audio sample.",
            status_code=422,
        )
    try:
        info = sf.info(io.BytesIO(content))
    except Exception as exc:
        raise ApiError(
            code="INVALID_VOICE_SAMPLE",
            message="Choose a valid WAV audio sample.",
            status_code=422,
        ) from exc
    if (
        info.format != "WAV"
        or not MIN_CLONE_DURATION_SECONDS <= info.duration <= MAX_CLONE_DURATION_SECONDS
    ):
        raise ApiError(
            code="INVALID_VOICE_SAMPLE",
            message="Voice samples must be WAV audio between 1 and 30 seconds long.",
            status_code=422,
        )

    voice_id = f"clone_{uuid.uuid4().hex}"
    storage = StorageService(get_settings())
    settings = get_settings()
    try:
        stored = storage.put_bytes(
            tenant_id=auth.tenant_id,
            document_id=auth.user_id,
            filename=f"{voice_id}.wav",
            content_type="audio/wav",
            payload=content,
        )
    except StorageServiceError as exc:
        raise ApiError(
            code="VOICE_STORAGE_UNAVAILABLE",
            message="Voice storage is temporarily unavailable.",
            status_code=503,
        ) from exc

    try:
        row = _get_or_create(db, auth, for_update=True)
        previous_clone_id = row.cloned_voice_id
        row.cloned_voice_id = voice_id
        row.cloned_voice_name = name
        row.voice = f"clone:{voice_id}"
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        storage.delete_tenant_object(
            tenant_id=auth.tenant_id,
            bucket=stored.bucket,
            object_key=stored.object_key,
            raise_on_error=False,
        )
        raise

    if previous_clone_id and previous_clone_id != voice_id:
        storage.delete_tenant_object(
            tenant_id=auth.tenant_id,
            bucket=settings.minio_bucket,
            object_key=_clone_object_key(auth, previous_clone_id),
            raise_on_error=False,
        )

    return {"voice_id": voice_id, "name": name}


@router.delete(
    "/clone/{voice_id}",
    dependencies=[Depends(require_permissions("queries:run"))],
)
def delete_cloned_voice(
    voice_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    row = _get_settings_row(db, auth, for_update=True)
    if row is None or row.cloned_voice_id != voice_id:
        raise ApiError(
            code="VOICE_CLONE_NOT_FOUND",
            message="The selected cloned voice was not found.",
            status_code=404,
        )

    settings = get_settings()
    try:
        StorageService(settings).delete_tenant_object(
            tenant_id=auth.tenant_id,
            bucket=settings.minio_bucket,
            object_key=_clone_object_key(auth, voice_id),
            raise_on_error=True,
        )
    except StorageServiceError as exc:
        db.rollback()
        raise ApiError(
            code="VOICE_STORAGE_UNAVAILABLE",
            message="The cloned voice could not be deleted. Retry deletion to finish cleanup.",
            status_code=503,
        ) from exc

    row.cloned_voice_id = None
    row.cloned_voice_name = None
    if row.voice == f"clone:{voice_id}":
        row.voice = "alba"
    db.commit()

    return {"status": "deleted"}
