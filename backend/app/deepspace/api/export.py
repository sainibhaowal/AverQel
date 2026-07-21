import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.core.errors import ApiError
from app.auth.rbac import require_permissions
from app.db.session import get_db
from app.query.repositories.chat import ChatRepository
from app.deepspace.integrations.export_service import DeepSpaceExportService

router = APIRouter(prefix="/deepspace/export", tags=["deepspace-export"])


@router.get(
    "/{conversation_id}",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def export_conversation(
    conversation_id: uuid.UUID,
    format: Literal["pdf", "docx", "md"] = Query("pdf"),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    repo = ChatRepository(db)
    conversation = repo.get_conversation(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        user_id=auth.user_id,
        kind="deepspace",
    )
    if not conversation:
        raise ApiError(
            code="CONVERSATION_NOT_FOUND",
            message="Conversation not found",
            status_code=404,
        )

    content_html = conversation.content_html or "<p>No content available.</p>"
    title = conversation.title or "DeepSpace Note"

    service = DeepSpaceExportService()

    if format == "pdf":
        file_obj = service.generate_pdf(content_html, title)
        media_type = "application/pdf"
        extension = "pdf"
    elif format == "docx":
        file_obj = service.generate_docx(content_html, title)
        media_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        extension = "docx"
    else:
        file_obj = service.generate_md(content_html)
        media_type = "text/markdown"
        extension = "md"

    filename = f"{title.replace(' ', '_')}_{conversation_id.hex[:8]}.{extension}"

    return Response(
        content=file_obj.getvalue(),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
