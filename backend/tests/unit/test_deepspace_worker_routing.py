from app.platform.worker.celery_app import celery_app


def test_deepspace_queue_dispatch_is_routed_away_from_model_workers():
    dispatch_route = celery_app.amqp.router.route(
        {}, "deepspace.dispatch_turn_queue", args=(), kwargs={}
    )
    model_route = celery_app.amqp.router.route({}, "deepspace.run", args=(), kwargs={})

    assert dispatch_route["queue"].name == "deepspace_control"
    assert model_route["queue"].name == "deepspace"
