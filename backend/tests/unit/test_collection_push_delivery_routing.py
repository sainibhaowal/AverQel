from app.platform.worker.celery_app import celery_app


def test_collection_push_outbox_is_routed_to_its_dedicated_worker() -> None:
    route = celery_app.amqp.router.route({}, "collections.dispatch_push_outbox", args=(), kwargs={})
    assert route["queue"].name == "collection_push"


def test_collection_push_outbox_remains_scheduled() -> None:
    schedule = celery_app.conf.beat_schedule
    assert any(
        entry.get("task") == "collections.dispatch_push_outbox" for entry in schedule.values()
    )
