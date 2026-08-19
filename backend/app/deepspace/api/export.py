import uuid
import re
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.core.errors import ApiError
from app.deepspace.integrations.export_service import DeepSpaceExportService
from app.deepspace.repositories.chat import DeepSpaceChatRepository
from app.platform.database.session import get_db

router = APIRouter(prefix="/deepspace/export", tags=["deepspace-export"])


def _download_content_disposition(*, title: str, extension: str) -> str:
    """Return a standards-safe attachment header for any user-authored title.

    HTTP header values must be Latin-1, while note titles are normal Unicode.
    Keep a conservative ASCII fallback for older clients and an RFC 5987 UTF-8
    filename for modern browsers.  Removing controls also prevents header
    injection through a note title.
    """

    clean_title = "".join(char for char in title if char.isprintable()).strip() or "DeepSpace Note"
    unicode_filename = f"{clean_title}.{extension}"
    ascii_filename = "".join(
        char
        if ord(char) < 128 and char not in {'\\', '"'} and not char.isspace()
        else "_"
        for char in unicode_filename
    )
    ascii_filename = re.sub(r"_+", "_", ascii_filename).strip(" ._") or (
        f"DeepSpace_Note.{extension}"
    )
    return (
        f'attachment; filename="{ascii_filename}"; '
        f"filename*=UTF-8''{quote(unicode_filename, safe='')}"
    )


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
    repo = DeepSpaceChatRepository(db)
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
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        extension = "docx"
    else:
        file_obj = service.generate_md(content_html)
        media_type = "text/markdown"
        extension = "md"

    filename_title = f"{title.replace(' ', '_')}_{conversation_id.hex[:8]}"

    return Response(
        content=file_obj.getvalue(),
        media_type=media_type,
        headers={
            "Content-Disposition": _download_content_disposition(
                title=filename_title,
                extension=extension,
            )
        },
    )
