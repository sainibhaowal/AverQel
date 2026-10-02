from __future__ import annotations

import fnmatch
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.ids import generate_uuid7_with_fallback
from app.documents.models.document import Document
from app.documents.models.organization import (
    DocumentClassificationApplication,
    DocumentClassificationRule,
    DocumentClassificationRun,
    DocumentFolderAssignment,
    DocumentTagAssignment,
)
from app.documents.repositories.documents import DocumentsRepository


@dataclass(slots=True)
class ClassificationApplicationResult:
    matched: bool
    applied: int
    actions: dict[str, bool]


class ClassificationService:
    """Tenant-scoped, idempotent classification execution shared by uploads and runs."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.documents = DocumentsRepository(db)

    @staticmethod
    def matches(rule: DocumentClassificationRule, document: Document) -> bool:
        if not fnmatch.fnmatch(document.filename.lower(), rule.filename_pattern.lower()):
            return False
        return not rule.content_type or rule.content_type == document.content_type

    def enabled_rules(self, tenant_id: uuid.UUID) -> list[DocumentClassificationRule]:
        return list(
            self.db.query(DocumentClassificationRule)
            .filter(
                DocumentClassificationRule.tenant_id == tenant_id,
                DocumentClassificationRule.enabled.is_(True),
            )
            .order_by(
                DocumentClassificationRule.priority.asc(),
                DocumentClassificationRule.created_at.asc(),
            )
            .all()
        )

    def apply_rule_to_document(
        self,
        *,
        rule: DocumentClassificationRule,
        document: Document,
        run_id: uuid.UUID | None = None,
        source: str = "upload",
        record_history: bool = True,
    ) -> ClassificationApplicationResult:
        if not self.matches(rule, document):
            return ClassificationApplicationResult(matched=False, applied=0, actions={})

        actions = {"tag_added": False, "folder_added": False}
        if rule.tag_id is not None:
            tag_exists = (
                self.db.query(DocumentTagAssignment.id)
                .filter(
                    DocumentTagAssignment.tenant_id == document.tenant_id,
                    DocumentTagAssignment.document_id == document.id,
                    DocumentTagAssignment.tag_id == rule.tag_id,
                )
                .first()
            )
            if tag_exists is None:
                self.db.add(
                    DocumentTagAssignment(
                        id=generate_uuid7_with_fallback(),
                        tenant_id=document.tenant_id,
                        document_id=document.id,
                        tag_id=rule.tag_id,
                    )
                )
                actions["tag_added"] = True

        if rule.folder_id is not None:
            folder_exists = (
                self.db.query(DocumentFolderAssignment.id)
                .filter(
                    DocumentFolderAssignment.tenant_id == document.tenant_id,
                    DocumentFolderAssignment.document_id == document.id,
                )
                .first()
            )
            if folder_exists is None:
                self.db.add(
                    DocumentFolderAssignment(
                        id=generate_uuid7_with_fallback(),
                        tenant_id=document.tenant_id,
                        document_id=document.id,
                        folder_id=rule.folder_id,
                    )
                )
                actions["folder_added"] = True

        applied = sum(1 for changed in actions.values() if changed)
        if record_history:
            self.db.add(
                DocumentClassificationApplication(
                    id=generate_uuid7_with_fallback(),
                    tenant_id=document.tenant_id,
                    rule_id=rule.id,
                    run_id=run_id,
                    document_id=document.id,
                    rule_name=rule.name,
                    source=source,
                    status="applied" if applied else "matched",
                    actions=actions,
                )
            )
        return ClassificationApplicationResult(matched=True, applied=applied, actions=actions)

    def apply_enabled_rules_to_document(self, document: Document) -> int:
        """Apply upload-time rules without making classification a pipeline blocker."""
        applied = 0
        for rule in self.enabled_rules(document.tenant_id):
            result = self.apply_rule_to_document(rule=rule, document=document, source="upload")
            applied += result.applied
        return applied

    def preview_rule(
        self,
        *,
        rule: DocumentClassificationRule,
        limit: int = 100,
        batch_size: int = 250,
    ) -> tuple[int, list[Document]]:
        matched = 0
        preview: list[Document] = []
        offset = 0
        while True:
            rows = self.documents.list_by_tenant(
                tenant_id=rule.tenant_id,
                skip=offset,
                limit=batch_size,
            )
            if not rows:
                break
            for document in rows:
                if self.matches(rule, document):
                    matched += 1
                    if len(preview) < limit:
                        preview.append(document)
            if len(rows) < batch_size:
                break
            offset += len(rows)
        return matched, preview

    def run_rule(
        self,
        *,
        run: DocumentClassificationRun,
        rule: DocumentClassificationRule,
        batch_size: int = 250,
    ) -> DocumentClassificationRun:
        run.status = "running"
        run.started_at = datetime.now(UTC)
        self.db.commit()
        offset = 0
        try:
            while True:
                rows = self.documents.list_by_tenant(
                    tenant_id=rule.tenant_id,
                    skip=offset,
                    limit=batch_size,
                )
                if not rows:
                    break
                for document in rows:
                    run.scanned_count += 1
                    if not self.matches(rule, document):
                        continue
                    run.matched_count += 1
                    try:
                        with self.db.begin_nested():
                            result = self.apply_rule_to_document(
                                rule=rule,
                                document=document,
                                run_id=run.id,
                                source=run.source,
                            )
                            self.db.flush()
                        run.applied_count += result.applied
                    except Exception as exc:  # one bad assignment must not stop the batch
                        run.failed_count += 1
                        self.db.add(
                            DocumentClassificationApplication(
                                id=generate_uuid7_with_fallback(),
                                tenant_id=document.tenant_id,
                                rule_id=rule.id,
                                run_id=run.id,
                                document_id=document.id,
                                rule_name=rule.name,
                                source=run.source,
                                status="failed",
                                actions={},
                                error_message=str(exc)[:2000],
                            )
                        )
                self.db.commit()
                if len(rows) < batch_size:
                    break
                offset += len(rows)
            run.status = "completed" if run.failed_count == 0 else "completed_with_errors"
        except Exception as exc:
            self.db.rollback()
            run.status = "failed"
            run.error_message = str(exc)[:2000]
        run.completed_at = datetime.now(UTC)
        self.db.commit()
        return run
