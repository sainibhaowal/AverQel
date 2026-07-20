from __future__ import annotations

import logging
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.core.errors import ApiError
from app.db.session import get_db
from app.models.query.conversation import Conversation
from app.models.query.feedback import Feedback
from app.models.query.message import Message
from app.schemas.system.feedback import FeedbackCreate, FeedbackResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse)
def submit_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    auth_ctx: AuthContext = Depends(get_auth_context),
) -> FeedbackResponse:
    message = db.execute(
        select(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Message.id == payload.message_id,
            Conversation.tenant_id == auth_ctx.tenant_id,
            Conversation.user_id == auth_ctx.user_id,
        )
    ).scalar_one_or_none()
    if message is None:
        raise ApiError(
            code="MESSAGE_NOT_FOUND",
            message="Message not found.",
            status_code=404,
        )

    feedback = db.execute(
        select(Feedback).where(Feedback.message_id == payload.message_id)
    ).scalar_one_or_none()

    if feedback is None:
        feedback = Feedback(
            message_id=payload.message_id,
            is_helpful=payload.is_helpful,
            reason=payload.reason,
        )
        db.add(feedback)
    else:
        feedback.is_helpful = payload.is_helpful
        feedback.reason = payload.reason

    try:
        db.commit()
        db.refresh(feedback)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning(
            "Failed to persist feedback.",
            extra={
                "tenant_id": str(auth_ctx.tenant_id),
                "user_id": str(auth_ctx.user_id),
                "message_id": str(payload.message_id),
            },
            exc_info=True,
        )
        raise ApiError(
            code="INTERNAL_SERVER_ERROR",
            message="Failed to save feedback.",
            status_code=500,
        ) from exc

    return FeedbackResponse.model_validate(feedback)
