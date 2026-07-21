from __future__ import annotations

from celery import Celery  # type: ignore[import-untyped]
from celery.schedules import crontab  # type: ignore[import-untyped]

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "aks-worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.worker.tasks_ingestion",
        "app.system.workers.tasks_maintenance",
        "app.integrations.workers.tasks_connectors",
        "app.deepspace.workers.tasks_proactive",
        "app.deepspace.workers.tasks",
        "app.integrations.workers.tasks_mcp",
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
        "app.integrations.workers.tasks_connectors.*": {"queue": "maintenance"},
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
        "connector-sync-all": {
            "task": "app.integrations.workers.tasks_connectors.sync_all_connectors",
            "schedule": crontab(minute=0),  # Every hour
        },
        "mcp-refresh-enabled-servers": {
            "task": "mcp.refresh_enabled_servers",
            "schedule": crontab(minute="*/2"),
        },
        **(
            {}
            if settings.deepspace_proactive_daemon_enabled
            else {
                "agent-proactive-monitor": {
                    "task": "app.deepspace.workers.tasks_proactive.monitor_agent_triggers",
                    "schedule": crontab(minute="*/5"),  # Every 5 minutes
                },
            }
        ),
    },
)

# Background task modules use the lightweight AgentExecutor
