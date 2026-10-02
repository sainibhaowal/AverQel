"""Structured, tenant-scoped DeepSpace document search and citation endpoint."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.deepspace.services.task_loop import DeepSpaceTaskLoopStore
from app.platform.database.session import get_db

router = APIRouter(prefix="/deepspace/documents", tags=["deepspace-documents"])


class DocumentQueryRequest(BaseModel):
    conversation_id: uuid.UUID
    query: str = Field(min_length=1, max_length=1000)
    file_id: uuid.UUID | None = None
    limit: int = Field(default=8, ge=1, le=20)


@router.post("/query", dependencies=[Depends(require_permissions("queries:run"))])
def query_documents(
    payload: DocumentQueryRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    store = DeepSpaceTaskLoopStore(db)
    entries = store.list_workspace_entries(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=payload.conversation_id,
    )
    files = entries.get("files", [])
    if payload.file_id:
        files = [item for item in files if str(item.get("id")) == str(payload.file_id)]
    needle = payload.query.casefold()
    passages: list[dict[str, Any]] = []
    for item in files[:50]:
        document = store.read_workspace_file(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            conversation_id=payload.conversation_id,
            file_id=str(item["id"]),
        )
        lines = str(document.get("content") or "").splitlines()
        for index, line in enumerate(lines):
            if needle in line.casefold():
                start, end = max(0, index - 1), min(len(lines), index + 2)
                passages.append(
                    {
                        "file_id": document["id"],
                        "filename": document["name"],
                        "line_start": start + 1,
                        "line_end": end,
                        "text": "\n".join(lines[start:end])[:4000],
                        "citation": f"file:{document['id']}#L{index + 1}",
                    }
                )
    return {
        "query": payload.query,
        "passages": passages[: payload.limit],
        "total_matches": len(passages),
    }
