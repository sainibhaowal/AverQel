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
        "app.system.workers.tasks_maintenance",
        "app.integrations.workers.tasks_connectors",
        "app.integrations.workers.tasks_mcp",
        "app.integrations.workers.tasks_mcp_catalog",
        "app.deepspace.workers.tasks",
        "app.deepspace.workers.library_uploads",
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
        "maintenance.process_data_deletion": {"queue": "maintenance"},
        "maintenance.retention_cleanup": {"queue": "maintenance"},
        "maintenance.heartbeat": {"queue": "maintenance"},
        "maintenance.storage_cleanup": {"queue": "maintenance"},
        "app.integrations.workers.tasks_connectors.*": {"queue": "maintenance"},
        "mcp.refresh_server_catalog": {"queue": "mcp_catalog"},
        "mcp.*": {"queue": "maintenance"},
        "mcp.sync_official_catalog": {"queue": "maintenance"},
        "deepspace.run": {"queue": "deepspace"},
        "deepspace.library_upload_finalize": {"queue": "deepspace"},
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
    },
)
