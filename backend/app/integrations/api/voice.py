from __future__ import annotations

from fastapi import APIRouter, Query
from livekit.api import AccessToken, VideoGrants

from app.core.config import get_settings

router = APIRouter(prefix="/voice", tags=["voice"])


@router.get("/token")
def get_voice_token(
    room: str = Query(..., description="Name of the room to join"),
    identity: str = Query(..., description="Identity of the participant"),
) -> dict[str, str]:
    settings = get_settings()
    token = (
        AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_grants(VideoGrants(room_join=True, room=room))
    )
    return {"token": token.to_jwt()}
