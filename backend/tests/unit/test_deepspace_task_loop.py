from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.deepspace.services.task_loop import DeepSpaceTaskLoopStore, _markdown_to_safe_html


def _task(task_id: str, status: str, dependencies: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=task_id,
        content=task_id,
        active_form=task_id,
        status=status,
        priority=0,
        metadata_json={"dependencies": dependencies or [], "evidence": []},
        created_at=None,
        updated_at=None,
    )


def test_task_check_reports_dependency_issues() -> None:
    store = DeepSpaceTaskLoopStore(SimpleNamespace())
    first = _task("first", "pending")
    second = _task("second", "pending", ["first"])
    store._tasks = lambda **kwargs: [first, second]  # type: ignore[method-assign]

    result = store.check_tasks(tenant_id=uuid4(), user_id=uuid4(), conversation_id=uuid4())

    assert result["complete"] is False
    assert result["dependency_issues"] == [{"task_id": "second", "dependencies": ["first"]}]
    with pytest.raises(ValueError, match="dependencies are incomplete"):
        store.mark_task(
            tenant_id=uuid4(),
            user_id=uuid4(),
            conversation_id=uuid4(),
            task_id="second",
            status="completed",
        )


def test_note_markdown_is_escaped_and_supports_safe_blocks() -> None:
    rendered = _markdown_to_safe_html("# Heading\n\n- item\n\n```python\nprint('<x>')\n```")

    assert "<h1>Heading</h1>" in rendered
    assert "<li>item</li>" in rendered
    assert "&lt;x&gt;" in rendered
    assert "<script" not in rendered
