"""Reconcile current ORM indexes and uniqueness with the migration schema.

This migration is additive. Older indexes and constraints are intentionally
retained because they may be used by existing deployments or query plans.
"""

from alembic import op

revision = "20261012_0007"
down_revision = "20261012_0006"
branch_labels = None
depends_on = None


_INDEXES = (
    ("audit_logs", "ix_audit_logs_action", ("action",), False),
    ("audit_logs", "ix_audit_logs_actor_user_id", ("actor_user_id",), False),
    ("audit_logs", "ix_audit_logs_resource_type", ("resource_type",), False),
    ("audit_logs", "ix_audit_logs_tenant_id", ("tenant_id",), False),
    ("audit_logs", "ix_audit_logs_trace_id", ("trace_id",), False),
    ("chunk_embeddings", "ix_chunk_embeddings_chunk_id", ("chunk_id",), False),
    ("chunk_embeddings", "ix_chunk_embeddings_document_id", ("document_id",), False),
    ("chunk_embeddings", "ix_chunk_embeddings_tenant_id", ("tenant_id",), False),
    ("collection_chat_reports", "ix_collection_chat_reports_status", ("status",), False),
    ("collection_devices", "ix_collection_devices_revoked_at", ("revoked_at",), False),
    (
        "collection_notifications",
        "ix_collection_notifications_recipient_created_id",
        ("recipient_user_id", "created_at", "id"),
        False,
    ),
    ("comments", "ix_comments_parent_id", ("parent_id",), False),
    ("conversations", "ix_conversations_tenant_id", ("tenant_id",), False),
    ("conversations", "ix_conversations_user_id", ("user_id",), False),
    ("data_deletions", "ix_data_deletions_requested_by_user_id", ("requested_by_user_id",), False),
    ("data_deletions", "ix_data_deletions_status", ("status",), False),
    ("data_deletions", "ix_data_deletions_tenant_id", ("tenant_id",), False),
    (
        "deepspace_artifact_jobs",
        "ix_deepspace_artifact_jobs_conversation_id",
        ("conversation_id",),
        False,
    ),
    (
        "deepspace_conversation_context_summaries",
        "ix_deepspace_conversation_context_summaries_conversation_id",
        ("conversation_id",),
        False,
    ),
    (
        "deepspace_conversation_context_summaries",
        "ix_deepspace_conversation_context_summaries_tenant_id",
        ("tenant_id",),
        False,
    ),
    (
        "deepspace_conversation_context_summaries",
        "ix_deepspace_conversation_context_summaries_user_id",
        ("user_id",),
        False,
    ),
    (
        "deepspace_conversation_retrieval_chunks",
        "ix_deepspace_conversation_retrieval_chunks_content_hash",
        ("content_hash",),
        False,
    ),
    (
        "deepspace_conversation_retrieval_chunks",
        "ix_deepspace_conversation_retrieval_chunks_conversation_id",
        ("conversation_id",),
        False,
    ),
    (
        "deepspace_conversation_retrieval_chunks",
        "ix_deepspace_conversation_retrieval_chunks_created_at",
        ("created_at",),
        False,
    ),
    (
        "deepspace_conversation_retrieval_chunks",
        "ix_deepspace_conversation_retrieval_chunks_indexed_at",
        ("indexed_at",),
        False,
    ),
    (
        "deepspace_conversation_retrieval_chunks",
        "ix_deepspace_conversation_retrieval_chunks_message_id",
        ("message_id",),
        False,
    ),
    (
        "deepspace_conversation_retrieval_chunks",
        "ix_deepspace_conversation_retrieval_chunks_message_version_id",
        ("message_version_id",),
        False,
    ),
    (
        "deepspace_conversation_retrieval_chunks",
        "ix_deepspace_conversation_retrieval_chunks_tenant_id",
        ("tenant_id",),
        False,
    ),
    (
        "deepspace_conversation_retrieval_chunks",
        "ix_deepspace_conversation_retrieval_chunks_user_id",
        ("user_id",),
        False,
    ),
    (
        "deepspace_mission_snapshots",
        "ix_deepspace_mission_snapshots_conversation_id",
        ("conversation_id",),
        False,
    ),
    ("deepspace_research_runs", "ix_deepspace_research_runs_user_id", ("user_id",), False),
    ("deepspace_schedule_runs", "ix_deepspace_schedule_runs_user_id", ("user_id",), False),
    ("deepspace_schedules", "ix_deepspace_schedules_conversation_id", ("conversation_id",), False),
    ("deepspace_schedules", "ix_deepspace_schedules_status", ("status",), False),
    ("document_chunks", "ix_document_chunks_chunk_index", ("chunk_index",), False),
    ("document_chunks", "ix_document_chunks_document_id", ("document_id",), False),
    ("document_chunks", "ix_document_chunks_tenant_id", ("tenant_id",), False),
    (
        "document_folder_assignments",
        "ix_document_folder_assignments_document_id",
        ("document_id",),
        False,
    ),
    (
        "document_folder_assignments",
        "ix_document_folder_assignments_folder_id",
        ("folder_id",),
        False,
    ),
    ("document_folders", "ix_document_folders_parent_id", ("parent_id",), False),
    ("document_saved_views", "ix_document_saved_views_user_id", ("user_id",), False),
    (
        "document_tag_assignments",
        "ix_document_tag_assignments_document_id",
        ("document_id",),
        False,
    ),
    ("document_tag_assignments", "ix_document_tag_assignments_tag_id", ("tag_id",), False),
    ("documents", "ix_documents_is_deleted", ("is_deleted",), False),
    ("documents", "ix_documents_parent_document_id", ("parent_document_id",), False),
    ("documents", "ix_documents_status", ("status",), False),
    ("documents", "ix_documents_tenant_id", ("tenant_id",), False),
    ("documents", "ix_documents_uploaded_by_user_id", ("uploaded_by_user_id",), False),
    ("idempotency_keys", "ix_idempotency_keys_idempotency_key", ("idempotency_key",), False),
    (
        "idempotency_keys",
        "ix_idempotency_keys_request_fingerprint",
        ("request_fingerprint",),
        False,
    ),
    ("idempotency_keys", "ix_idempotency_keys_tenant_id", ("tenant_id",), False),
    ("ingestion_jobs", "ix_ingestion_jobs_document_id", ("document_id",), False),
    ("ingestion_jobs", "ix_ingestion_jobs_status", ("status",), False),
    ("ingestion_jobs", "ix_ingestion_jobs_tenant_id", ("tenant_id",), False),
    ("messages", "ix_messages_conversation_id", ("conversation_id",), False),
    ("pinned_findings", "ix_pinned_findings_chunk_id", ("chunk_id",), False),
    ("queries", "ix_queries_tenant_id", ("tenant_id",), False),
    ("queries", "ix_queries_trace_id", ("trace_id",), False),
    ("queries", "ix_queries_user_id", ("user_id",), False),
    ("query_citations", "ix_query_citations_chunk_id", ("chunk_id",), False),
    ("query_citations", "ix_query_citations_document_id", ("document_id",), False),
    ("query_citations", "ix_query_citations_query_id", ("query_id",), False),
    ("query_citations", "ix_query_citations_tenant_id", ("tenant_id",), False),
    ("refresh_tokens", "ix_refresh_tokens_tenant_id", ("tenant_id",), False),
    ("refresh_tokens", "ix_refresh_tokens_token_family_id", ("token_family_id",), False),
    ("refresh_tokens", "ix_refresh_tokens_user_id", ("user_id",), False),
    (
        "storage_lifecycle_items",
        "ix_storage_lifecycle_items_dependency_group_id",
        ("dependency_group_id",),
        False,
    ),
    (
        "storage_lifecycle_items",
        "ix_storage_lifecycle_items_last_meaningful_activity_at",
        ("last_meaningful_activity_at",),
        False,
    ),
    ("usage_records", "ix_usage_records_created_at", ("created_at",), False),
    ("usage_records", "ix_usage_records_operation", ("operation",), False),
    ("user_roles", "ix_user_roles_role_id", ("role_id",), False),
    ("user_roles", "ix_user_roles_tenant_id", ("tenant_id",), False),
    ("user_roles", "ix_user_roles_user_id", ("user_id",), False),
    ("users", "ix_users_tenant_id", ("tenant_id",), False),
)


def _create_index(table: str, name: str, columns: tuple[str, ...], unique: bool) -> None:
    qualifier = "UNIQUE " if unique else ""
    column_sql = ", ".join(columns)
    op.execute(f"CREATE {qualifier}INDEX IF NOT EXISTS {name} " f"ON {table} ({column_sql})")


def upgrade() -> None:
    for table, name, columns, unique in _INDEXES:
        _create_index(table, name, columns, unique)

    # Replace the historical non-unique index with the current unique index.
    op.execute("DROP INDEX IF EXISTS ix_document_share_links_token_hash")
    _create_index(
        "document_share_links", "ix_document_share_links_token_hash", ("token_hash",), True
    )
    _create_index("feedbacks", "ix_feedbacks_message_id", ("message_id",), True)
    _create_index("roles", "ix_roles_name", ("name",), True)

    op.execute("""
        DO $$ BEGIN
            ALTER TABLE pinned_findings
            ADD CONSTRAINT uq_pinned_findings_tenant_user_query_chunk
            UNIQUE (tenant_id, user_id, query_id, chunk_id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """)


def downgrade() -> None:
    # Indexes are intentionally retained on downgrade for compatibility.
    pass
