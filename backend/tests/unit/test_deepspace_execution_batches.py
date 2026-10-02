import asyncio

from app.deepspace.services.execution_batches import plan_execution_batches


def test_execution_batches_keep_writes_as_ordering_barriers() -> None:
    calls = [{"id": "read-1"}, {"id": "read-2"}, {"id": "write"}, {"id": "read-3"}]

    batches = plan_execution_batches(calls, is_read=lambda call: call["id"].startswith("read"))

    assert [(batch.parallel, [call["id"] for call in batch.calls]) for batch in batches] == [
        (True, ["read-1", "read-2"]),
        (False, ["write"]),
        (True, ["read-3"]),
    ]


def test_parallel_batch_can_be_awaited_without_reordering_inputs() -> None:
    async def run() -> list[str]:
        calls = [{"id": "read-1"}, {"id": "read-2"}]
        batch = plan_execution_batches(calls, is_read=lambda _: True)[0]
        return await asyncio.gather(*(asyncio.sleep(0, result=call["id"]) for call in batch.calls))

    assert asyncio.run(run()) == ["read-1", "read-2"]
