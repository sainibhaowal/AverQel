from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from livekit.api import AccessToken, VideoGrants

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.core.config import get_settings
from app.core.errors import ApiError

router = APIRouter(prefix="/voice", tags=["voice"])


@router.get(
    "/token",
    dependencies=[Depends(require_permissions("queries:run"))],
)
def get_voice_token(
    room: str = Query(..., description="Name of the room to join"),
    identity: str = Query(..., description="Identity of the participant"),
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, str]:
    expected_identity = f"user-{auth.user_id}"
    if identity != expected_identity:
        raise ApiError(
            code="FORBIDDEN",
            message="Voice identity must match the authenticated user.",
            status_code=403,
        )
    settings = get_settings()
    token = (
        AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_grants(VideoGrants(room_join=True, room=room))
    )
    return {"token": token.to_jwt()}
