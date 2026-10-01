from __future__ import annotations

from celery import Celery  # type: ignore[import-untyped]
from celery.schedules import crontab  # type: ignore[import-untyped]

from app.core.config import get_settings
from app.platform.database import model_registry  # noqa: F401

settings = get_settings()

celery_app = Celery(
    "aks-worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.ingestion.workers.tasks",
        "app.documents.workers.tasks_webhooks",
        "app.documents.workers.tasks_collection_security",
        "app.documents.workers.tasks_classification",
        "app.system.workers.tasks_maintenance",
        "app.system.workers.tasks_retention",
        "app.integrations.workers.tasks_connectors",
        "app.integrations.workers.tasks_mcp",
        "app.integrations.workers.tasks_mcp_catalog",
        "app.deepspace.workers.tasks",
        "app.deepspace.workers.library_uploads",
        "app.deepspace.workers.schedules",
    ],
)

celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_track_started=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_default_queue="ingestion_light",
    task_routes={
        "ingestion.process_job": {"queue": "ingestion_heavy"},
        "ingestion.ping": {"queue": "ingestion_light"},
        "documents.*": {"queue": "maintenance"},
        "maintenance.process_data_deletion": {"queue": "maintenance"},
        "maintenance.retention_cleanup": {"queue": "maintenance"},
        "maintenance.heartbeat": {"queue": "maintenance"},
        "maintenance.storage_cleanup": {"queue": "maintenance"},
        "maintenance.collection_chat_media_orphan_sweep": {"queue": "maintenance"},
        "maintenance.deepspace_context_cleanup": {"queue": "maintenance"},
        "maintenance.storage_retention_scan": {"queue": "maintenance"},
        "app.integrations.workers.tasks_connectors.*": {"queue": "maintenance"},
        "mcp.refresh_server_catalog": {"queue": "mcp_catalog"},
        "mcp.*": {"queue": "maintenance"},
        "mcp.sync_official_catalog": {"queue": "maintenance"},
        "deepspace.run": {"queue": "deepspace"},
        "deepspace.dispatch_turn_queue": {"queue": "deepspace"},
        # Large Library imports are intentionally isolated from interactive
        # DeepSpace chat turns.  The dedicated worker has concurrency one.
        "deepspace.library_upload_finalize": {"queue": "library_uploads"},
        "deepspace.library_dataset_profile": {"queue": "dataset_indexing"},
        "deepspace.library_media_derivative": {"queue": "media_derivatives"},
        "deepspace.dispatch_schedules": {"queue": "deepspace"},
        "deepspace.artifact_create": {"queue": "deepspace"},
        "deepspace.index_conversation": {"queue": "dataset_indexing"},
    },
    beat_schedule={
        "maintenance-heartbeat": {
            "task": "maintenance.heartbeat",
            "schedule": crontab(minute="*/5"),
        },
        "maintenance-retention-cleanup": {
            "task": "maintenance.retention_cleanup",
            "schedule": crontab(hour=2, minute=0),
        },
        "maintenance-storage-cleanup": {
            "task": "maintenance.storage_cleanup",
            "schedule": crontab(minute="*/5"),
        },
        "maintenance-collection-chat-media-orphan-sweep": {
            "task": "maintenance.collection_chat_media_orphan_sweep",
            "schedule": crontab(minute="*/30"),
        },
        "maintenance-deepspace-context-cleanup": {
            "task": "maintenance.deepspace_context_cleanup",
            "schedule": crontab(hour=3, minute=30),
        },
        # Policy thresholds are evaluated monthly; the user setting controls
        # the age. Automatic archive is opt-in for local/staging only and
        # permanent purge has no worker or schedule.
        "maintenance-storage-retention-scan": {
            "task": "maintenance.storage_retention_scan",
            "schedule": crontab(hour=4, minute=0, day_of_month="1"),
        },
        "documents-classification-schedules": {
            "task": "documents.apply_classification_schedules",
            "schedule": crontab(minute="*/5"),
        },
        "documents-webhook-outbox": {
            "task": "documents.dispatch_pending_webhook_deliveries",
            "schedule": crontab(minute="*"),
        },
        "documents-collection-push-outbox": {
            "task": "collections.dispatch_push_outbox",
            "schedule": crontab(minute="*"),
        },
        "connector-sync-all": {
            "task": "app.integrations.workers.tasks_connectors.sync_all_connectors",
            "schedule": crontab(minute=0),  # Every hour
        },
        "mcp-refresh-enabled-servers": {
            "task": "mcp.refresh_enabled_servers",
            "schedule": crontab(minute="*/2"),
        },
        "mcp-sync-official-catalog": {
            "task": "mcp.sync_official_catalog",
            "schedule": crontab(hour=3, minute=17),
        },
        "deepspace-dispatch-schedules": {
            "task": "deepspace.dispatch_schedules",
            "schedule": crontab(minute="*"),
        },
    },
)
