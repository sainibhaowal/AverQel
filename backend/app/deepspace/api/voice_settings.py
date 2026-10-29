"""Voice Studio settings API for DeepSpace."""

from __future__ import annotations

import io
import logging
import os
import struct
import threading
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.core.errors import ApiError
from app.deepspace.models.voice_settings import DeepSpaceVoiceSettings
from app.platform.database.session import get_db

logger = logging.getLogger("deepspace-voice-settings")

router = APIRouter(prefix="/deepspace/voice", tags=["deepspace-voice"])

CLONE_DIR = Path(os.getenv("AVERQEL_VOICE_CLONE_DIR", "/app/data/voice-clones"))

# Global model cache
_tts_model = None
_tts_model_lock = threading.Lock()
_tts_generation_lock = threading.Lock()


def _get_tts_model() -> Any:
    global _tts_model
    if _tts_model is None:
        with _tts_model_lock:
            if _tts_model is None:
                from pocket_tts import TTSModel

                _tts_model = TTSModel.load_model()
    return _tts_model


def _generate_test_samples(
    tts: Any,
    voice: str,
    text: str,
    clone_path: str | None,
) -> np.ndarray:
    """Serialize Pocket TTS access because its model state is not thread-safe."""
    with _tts_generation_lock:
        if voice.startswith("clone:"):
            if clone_path and os.path.exists(clone_path):
                voice_state = tts.get_state_for_audio_prompt(clone_path)
            else:
                voice_state = tts.get_state_for_audio_prompt("alba")
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
    voice: str = "alba"
    speed: float = 1.0
    pitch: float = 1.0
    volume: float = 1.0
    clonedVoiceId: str | None = None  # noqa: N815
    clonedVoiceName: str | None = None  # noqa: N815


def _get_or_create(db: Session, auth: AuthContext) -> DeepSpaceVoiceSettings:
    row = db.get(DeepSpaceVoiceSettings, auth.user_id)
    if row is None:
        row = DeepSpaceVoiceSettings(
            user_id=auth.user_id,
            tenant_id=auth.tenant_id,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


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
    row = _get_or_create(db, auth)
    row.voice = payload.voice
    row.speed = payload.speed
    row.pitch = payload.pitch
    row.volume = payload.volume
    row.cloned_voice_id = payload.clonedVoiceId
    row.cloned_voice_name = payload.clonedVoiceName
    db.commit()
    db.refresh(row)
    return _row_to_dict(row)


@router.post(
    "/test",
    dependencies=[Depends(require_permissions("queries:run"))],
)
def test_voice(
    payload: dict[str, Any],
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Any:
    import torch

    # Use multi-threading on CPU for significantly faster generation (pocket-tts hardcodes 1 by default)
    torch.set_num_threads(min(4, max(2, os.cpu_count() or 2)))

    text = payload.get("text", "Hello! How does this voice sound?")
    voice = payload.get("voice", "alba")
    speed = float(payload.get("speed", 1.0))
    # Keep accepting pitch for saved-settings compatibility; Pocket TTS does not
    # currently provide pitch shifting, so the UI states that this is unsupported.
    volume = float(payload.get("volume", 1.0))

    try:
        tts = _get_tts_model()

        clone_path = None
        # Resolve cloned voice only from this authenticated user's saved setting.
        if voice.startswith("clone:"):
            clone_id = voice.split(":", 1)[1]
            row = db.get(DeepSpaceVoiceSettings, auth.user_id)
            if (
                row
                and row.cloned_voice_id == clone_id
                and row.cloned_voice_path
                and os.path.exists(row.cloned_voice_path)
            ):
                clone_path = row.cloned_voice_path
            else:
                search_dir = CLONE_DIR / str(auth.tenant_id) / str(auth.user_id)
                clone_path = next((str(path) for path in search_dir.glob(f"{clone_id}*")), None)

            if not clone_path:
                logger.warning("Cloned voice file not found: %s, falling back to alba", clone_id)
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
    except Exception as e:
        logger.error("Voice test failed: %s", e, exc_info=True)
        raise ApiError(
            code="VOICE_TEST_FAILED",
            message=f"Voice test failed: {str(e)}",
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
    import time

    voice_id = f"clone_{auth.user_id}_{int(time.time())}"
    clone_dir = CLONE_DIR / str(auth.tenant_id) / str(auth.user_id)
    clone_dir.mkdir(parents=True, exist_ok=True)
    clone_path = clone_dir / f"{voice_id}.ogg"
    content = await audio.read()
    clone_path.write_bytes(content)

    row = _get_or_create(db, auth)
    row.cloned_voice_id = voice_id
    row.cloned_voice_name = name
    row.cloned_voice_path = str(clone_path)
    row.voice = f"clone:{voice_id}"
    db.commit()
    db.refresh(row)

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
    row = _get_or_create(db, auth)
    if row.cloned_voice_id == voice_id and row.cloned_voice_path:
        path = Path(row.cloned_voice_path)
        if path.exists():
            path.unlink()

    if row.cloned_voice_id == voice_id:
        row.cloned_voice_id = None
        row.cloned_voice_name = None
        row.cloned_voice_path = None
        if row.voice.startswith("clone:"):
            row.voice = "alba"
        db.commit()

    return {"status": "deleted"}
