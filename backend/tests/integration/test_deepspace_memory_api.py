from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from app.models.deepspace.agent_memory import AgentMemory
from app.services.deepspace.memory.memory_service import MemoryService
from tests.conftest import SeededUser


def _auth_headers(
    seeded: SeededUser, *, roles: tuple[str, ...] = ("admin",)
) -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles=set(roles),
        settings=get_settings(),
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }


def test_deepspace_memory_list_delete_and_retrieve(
    client,
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "Memory API Tenant",
        "memory@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded)
    service = MemoryService(db_session)

    asyncio.run(
        service.store_fact(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            key="gmail_summary",
            value="Check the CEO follow-up email and draft a reply.",
            scope="user",
            tags=["gmail", "draft"],
        )
    )
    asyncio.run(
        service.store_fact(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            key="news_watch",
            value="Fetch the latest AI news every morning.",
            scope="persistent",
            tags=["web", "recurring"],
        )
    )

    fact = asyncio.run(
        service.retrieve_fact(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            key="gmail_summary",
        )
    )
    assert fact == "Check the CEO follow-up email and draft a reply."

    list_response = client.get("/api/v1/deepspace/chats/memory", headers=headers)
    assert list_response.status_code == 200
    memories = list_response.json()
    assert len(memories) == 2
    assert memories[0]["key"] in {"gmail_summary", "news_watch"}
    assert memories[0]["tags"]

    delete_response = client.delete(
        "/api/v1/deepspace/chats/memory/gmail_summary",
        headers=headers,
    )
    assert delete_response.status_code == 204

    after_response = client.get("/api/v1/deepspace/chats/memory", headers=headers)
    assert after_response.status_code == 200
    after_memories = after_response.json()
    assert len(after_memories) == 1
    assert after_memories[0]["key"] == "news_watch"


def test_deepspace_memory_uses_real_embeddings_scoring_and_dedupes(
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "Memory Intelligence Tenant",
        "semantic-memory@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    service = MemoryService(db_session)

    first_id = asyncio.run(
        service.store_fact(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            key="gmail_reply_preference",
            value="For urgent Gmail threads, draft a concise reply and ask before sending.",
            scope="user",
            tags=["gmail", "preference"],
            importance_score=0.9,
            metadata_json={"source": "test"},
        )
    )
    second_id = asyncio.run(
        service.store_fact(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            key="daily_market_watch",
            value="Every morning, scan market news and summarize material AI infrastructure moves.",
            scope="user",
            tags=["recurring"],
        )
    )
    duplicate_id = asyncio.run(
        service.store_fact(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            key="gmail_reply_preference",
            value="For urgent Gmail threads, draft a concise reply and ask before sending.",
            scope="user",
            tags=["workflow"],
        )
    )

    assert duplicate_id == first_id
    assert second_id != first_id

    results = asyncio.run(
        service.search_memories(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            query="urgent gmail reply",
            limit=2,
        )
    )

    assert results
    assert results[0]["key"] == "gmail_reply_preference"
    assert results[0]["relevance_score"] > 0
    assert results[0]["semantic_score"] >= 0
    assert results[0]["lexical_score"] > 0
    assert results[0]["access_count"] >= 1
    assert results[0]["embedding_provider"]
    assert results[0]["embedding_model"]
    assert results[0]["pgvector_ready"] is True
    assert results[0]["decay_score"] is not None
    assert results[0]["metadata"]["source"] == "test"

    report = asyncio.run(
        service.evaluate_memory_quality(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            sample_queries=["urgent gmail reply"],
        )
    )
    assert report["memory_count"] == 2
    assert report["embedding_coverage"] == 1.0
    assert report["pgvector_count"] == 2
    assert report["duplicate_count"] == 0
    assert report["average_decay_score"] >= 0.0
    assert report["sample_queries"][0]["matches"] > 0


def test_deepspace_memory_short_circuits_exact_duplicate_embedding_calls(
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    seeded = seed_user(
        "Duplicate Memory Tenant",
        "duplicate-memory@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    service = MemoryService(db_session)
    calls = {"embed": 0}
    embedding_dimension = get_settings().embedding_dimension

    def fake_embed_text(
        self, text: str, *, tenant_id: str, user_id: str
    ):  # noqa: ANN001
        calls["embed"] += 1
        return (
            [0.25] * embedding_dimension,
            {
                "provider": "fake",
                "model": "fake-model",
                "fallback_used": False,
                "failure_code": None,
            },
        )

    monkeypatch.setattr(MemoryService, "_embed_text", fake_embed_text)

    first_id = asyncio.run(
        service.store_fact(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            key="duplicate_note",
            value="Keep this fact for the current workspace.",
            scope="user",
            tags=["workspace"],
        )
    )
    second_id = asyncio.run(
        service.store_fact(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            key="duplicate_note",
            value="Keep this fact for the current workspace.",
            scope="user",
            tags=["workspace", "duplicate"],
        )
    )

    assert first_id == second_id
    assert calls["embed"] == 1


def test_deepspace_memory_global_scope_is_visible_and_reported(
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "Shared Memory Tenant",
        "shared-memory@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    service = MemoryService(db_session)

    asyncio.run(
        service.store_fact(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            key="team_playbook",
            value="Use the orchestrator for multi-step work and store the result in memory.",
            scope="global",
            tags=["workflow", "orchestration"],
        )
    )
    asyncio.run(
        service.store_fact(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            key="team_playbook",
            value="Use the orchestrator for multi-step work and store the result in memory.",
            scope="global",
            tags=["workflow", "orchestration", "duplicate"],
        )
    )

    retrieved = asyncio.run(
        service.retrieve_fact(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            key="team_playbook",
        )
    )
    assert (
        retrieved
        == "Use the orchestrator for multi-step work and store the result in memory."
    )

    memories = asyncio.run(
        service.list_all_memories(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
        )
    )
    assert len(memories) == 1
    assert memories[0]["scope"] == "global"

    report = asyncio.run(
        service.evaluate_memory_quality(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
        )
    )
    assert report["scope_breakdown"] == {"global": 1}
    assert report["memory_count"] == 1
    assert report["duplicate_count"] == 0


def test_deepspace_memory_session_scope_is_visible_searchable_and_deletable(
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "Session Memory Tenant",
        "session-memory@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    service = MemoryService(db_session)

    asyncio.run(
        service.store_fact(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            key="session_note",
            value="Keep this prompt in mind for the current session only.",
            scope="session",
            tags=["session", "draft"],
        )
    )
    asyncio.run(
        service.store_fact(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            key="persistent_note",
            value="Keep this prompt available across sessions.",
            scope="persistent",
            tags=["user"],
        )
    )

    memories = asyncio.run(
        service.list_all_memories(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
        )
    )
    assert [item["scope"] for item in memories] == ["session", "user"]

    retrieved = asyncio.run(
        service.retrieve_fact(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            key="session_note",
        )
    )
    assert retrieved == "Keep this prompt in mind for the current session only."

    results = asyncio.run(
        service.search_memories(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            query="current session prompt",
            limit=2,
        )
    )
    assert results
    assert results[0]["scope"] == "session"
    assert results[0]["relevance_score"] >= results[-1]["relevance_score"]

    delete_response = asyncio.run(
        service.forget_memory(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            key="session_note",
        )
    )
    assert delete_response is True

    after = asyncio.run(
        service.list_all_memories(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
        )
    )
    assert [item["key"] for item in after] == ["persistent_note"]


def test_deepspace_memory_search_collapses_duplicate_rows(
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    seeded = seed_user(
        "Duplicate Search Tenant",
        "duplicate-search@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    service = MemoryService(db_session)
    dimension = get_settings().embedding_dimension
    shared_hash = "duplicate-search-hash"

    memory_a = AgentMemory(
        id="memory-a",
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        key="workflow_note",
        value="Prefer concise answers with approval before sending.",
        embedding=[0.11] * dimension,
        embedding_vector=[0.11] * dimension,
        embedding_provider="test",
        embedding_model="test-model",
        embedding_version="test-v1",
        content_hash=shared_hash,
        importance_score=0.5,
        access_count=0,
        metadata_json={},
        scope="user",
        tags=["workflow"],
    )
    memory_b = AgentMemory(
        id="memory-b",
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        key="workflow_note_copy",
        value="Prefer concise answers with approval before sending.",
        embedding=[0.11] * dimension,
        embedding_vector=[0.11] * dimension,
        embedding_provider="test",
        embedding_model="test-model",
        embedding_version="test-v1",
        content_hash=shared_hash,
        importance_score=0.4,
        access_count=0,
        metadata_json={},
        scope="user",
        tags=["workflow", "copy"],
    )
    db_session.add(memory_a)
    db_session.add(memory_b)
    db_session.commit()

    def fake_pgvector_search(**kwargs):  # noqa: ANN001
        _ = kwargs
        return [
            (db_session.get(AgentMemory, "memory-a"), 0.1),
            (db_session.get(AgentMemory, "memory-b"), 0.2),
        ]

    monkeypatch.setattr(
        MemoryService,
        "_search_candidates_with_pgvector",
        staticmethod(fake_pgvector_search),
    )
    monkeypatch.setattr(
        MemoryService,
        "_embed_text",
        lambda self, text, *, tenant_id, user_id: (
            [0.11] * dimension,
            {
                "provider": "test",
                "model": "test-model",
                "fallback_used": False,
                "failure_code": None,
            },
        ),
    )

    results = asyncio.run(
        service.search_memories(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            query="approval before sending",
            limit=5,
        )
    )

    assert len(results) == 1
    assert results[0]["key"] == "workflow_note"
    assert results[0]["relevance_score"] > 0


def test_deepspace_memory_decay_scores_track_recency(
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    seeded = seed_user(
        "Decay Memory Tenant",
        "decay-memory@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    service = MemoryService(db_session)
    dimension = get_settings().embedding_dimension
    old_timestamp = datetime.now(UTC) - timedelta(days=30)
    fresh_timestamp = datetime.now(UTC)

    old_memory = AgentMemory(
        id="decay-old",
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        key="old_note",
        value="Review the recurring workflow preference note.",
        embedding=[0.14] * dimension,
        embedding_vector=[0.14] * dimension,
        embedding_provider="test",
        embedding_model="test-model",
        embedding_version="test-v1",
        content_hash="decay-old-hash",
        importance_score=0.4,
        access_count=0,
        metadata_json={},
        scope="user",
        tags=["workflow"],
        created_at=old_timestamp,
        updated_at=old_timestamp,
        last_accessed_at=old_timestamp,
    )
    fresh_memory = AgentMemory(
        id="decay-fresh",
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        key="fresh_note",
        value="Review the recurring workflow preference note.",
        embedding=[0.14] * dimension,
        embedding_vector=[0.14] * dimension,
        embedding_provider="test",
        embedding_model="test-model",
        embedding_version="test-v1",
        content_hash="decay-fresh-hash",
        importance_score=0.4,
        access_count=0,
        metadata_json={},
        scope="user",
        tags=["workflow"],
        created_at=fresh_timestamp,
        updated_at=fresh_timestamp,
        last_accessed_at=fresh_timestamp,
    )
    db_session.add(old_memory)
    db_session.add(fresh_memory)
    db_session.commit()

    monkeypatch.setattr(
        MemoryService,
        "_search_candidates_with_pgvector",
        staticmethod(
            lambda **kwargs: [
                (db_session.get(AgentMemory, "decay-old"), 0.1),
                (db_session.get(AgentMemory, "decay-fresh"), 0.1),
            ]
        ),
    )
    monkeypatch.setattr(db_session, "commit", lambda: None)

    results = asyncio.run(
        service.search_memories(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            query="recurring workflow preference",
            limit=2,
        )
    )
    result_by_key = {item["key"]: item for item in results}
    assert (
        result_by_key["old_note"]["decay_score"]
        > result_by_key["fresh_note"]["decay_score"]
    )
    assert result_by_key["old_note"]["decay_score"] > 0.0


def test_deepspace_memory_cleanup_endpoint_collapses_duplicate_rows(
    client,
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "Cleanup Memory Tenant",
        "cleanup-memory@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded)
    dimension = get_settings().embedding_dimension
    shared_hash = "cleanup-memory-hash"

    memory_a = AgentMemory(
        id="cleanup-memory-a",
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        key="cleanup_note",
        value="Prefer short replies and explicit approval before sending.",
        embedding=[0.12] * dimension,
        embedding_vector=[0.12] * dimension,
        embedding_provider="test",
        embedding_model="test-model",
        embedding_version="test-v1",
        content_hash=shared_hash,
        importance_score=0.4,
        access_count=1,
        metadata_json={"source": "seed-a"},
        scope="user",
        tags=["workflow"],
    )
    memory_b = AgentMemory(
        id="cleanup-memory-b",
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        key="cleanup_note_copy",
        value="Prefer short replies and explicit approval before sending.",
        embedding=[0.12] * dimension,
        embedding_vector=[0.12] * dimension,
        embedding_provider="test",
        embedding_model="test-model",
        embedding_version="test-v1",
        content_hash=shared_hash,
        importance_score=0.9,
        access_count=3,
        metadata_json={"source": "seed-b"},
        scope="user",
        tags=["workflow", "duplicate"],
    )
    db_session.add(memory_a)
    db_session.add(memory_b)
    db_session.commit()

    response = client.post("/api/v1/deepspace/chats/memory/cleanup", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["memory_count"] == 2
    assert payload["duplicate_groups"] == 1
    assert payload["removed_count"] == 1
    assert payload["kept_count"] == 1

    db_session.expire_all()
    remaining = asyncio.run(
        MemoryService(db_session).list_all_memories(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
        )
    )
    assert len(remaining) == 1
    assert remaining[0]["key"] in {"cleanup_note", "cleanup_note_copy"}
    assert remaining[0]["metadata"]["duplicate_group_count"] == 2
    assert len(remaining[0]["metadata"]["duplicate_memory_ids"]) == 1
    assert remaining[0]["metadata"]["duplicate_memory_ids"][0] in {
        "cleanup-memory-a",
        "cleanup-memory-b",
    }


def test_deepspace_memory_cleanup_stale_endpoint_prunes_session_memory_only(
    client,
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "Stale Memory Tenant",
        "stale-memory@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded)
    old_timestamp = datetime.now(UTC) - timedelta(days=10)
    fresh_timestamp = datetime.now(UTC)

    stale_session = AgentMemory(
        id="stale-session-memory",
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        key="session_note",
        value="Temporary session note that should expire.",
        embedding=[0.2] * get_settings().embedding_dimension,
        embedding_vector=[0.2] * get_settings().embedding_dimension,
        embedding_provider="test",
        embedding_model="test-model",
        embedding_version="test-v1",
        content_hash="stale-session-hash",
        importance_score=0.2,
        access_count=0,
        metadata_json={},
        scope="session",
        tags=["session"],
        created_at=old_timestamp,
        updated_at=old_timestamp,
        last_accessed_at=old_timestamp,
    )
    fresh_user = AgentMemory(
        id="fresh-user-memory",
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        key="user_note",
        value="Durable user memory should remain.",
        embedding=[0.3] * get_settings().embedding_dimension,
        embedding_vector=[0.3] * get_settings().embedding_dimension,
        embedding_provider="test",
        embedding_model="test-model",
        embedding_version="test-v1",
        content_hash="fresh-user-hash",
        importance_score=0.8,
        access_count=2,
        metadata_json={},
        scope="user",
        tags=["user"],
        created_at=fresh_timestamp,
        updated_at=fresh_timestamp,
        last_accessed_at=fresh_timestamp,
    )
    db_session.add(stale_session)
    db_session.add(fresh_user)
    db_session.commit()

    response = client.post(
        "/api/v1/deepspace/chats/memory/cleanup-stale", headers=headers
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["memory_count"] == 1
    assert payload["removed_count"] == 1
    assert payload["retained_count"] == 0
    assert payload["retention_days"] == 7
    assert payload["stale_memory_ids"] == ["stale-session-memory"]

    db_session.expire_all()
    memories = asyncio.run(
        MemoryService(db_session).list_all_memories(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
        )
    )
    assert len(memories) == 1
    assert memories[0]["key"] == "user_note"

    report = asyncio.run(
        MemoryService(db_session).evaluate_memory_quality(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
        )
    )
    assert report["stale_count"] == 0
    assert report["retention_breakdown"] == {"persistent": 1}


def test_deepspace_memory_retention_endpoint_reports_decay_and_policy(
    client,
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "Retention Memory Tenant",
        "retention-memory@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded)
    service = MemoryService(db_session)

    asyncio.run(
        service.store_fact(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            key="retention_note",
            value="Keep a durable memory for long-lived preferences.",
            scope="user",
            tags=["user"],
            importance_score=0.7,
        )
    )

    response = client.get("/api/v1/deepspace/chats/memory/retention", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["memory_count"] == 1
    assert payload["average_decay_score"] >= 0.0
    assert payload["session_retention_days"] == 7
    assert payload["retention_policy"]["decay_half_life_days"] == 120.0


def test_deepspace_memory_lifecycle_endpoint_reports_stale_preview_without_deleting(
    client,
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "Lifecycle Memory Tenant",
        "lifecycle-memory@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded)
    old_timestamp = datetime.now(UTC) - timedelta(days=10)
    fresh_timestamp = datetime.now(UTC)

    stale_session = AgentMemory(
        id="lifecycle-stale-memory",
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        key="session_note",
        value="Temporary session note that should show up in lifecycle preview.",
        embedding=[0.21] * get_settings().embedding_dimension,
        embedding_vector=[0.21] * get_settings().embedding_dimension,
        embedding_provider="test",
        embedding_model="test-model",
        embedding_version="test-v1",
        content_hash="lifecycle-session-hash",
        importance_score=0.2,
        access_count=0,
        metadata_json={},
        scope="session",
        tags=["session"],
        created_at=old_timestamp,
        updated_at=old_timestamp,
        last_accessed_at=old_timestamp,
    )
    fresh_user = AgentMemory(
        id="lifecycle-fresh-memory",
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        key="user_note",
        value="Durable user memory should remain in the lifecycle report.",
        embedding=[0.31] * get_settings().embedding_dimension,
        embedding_vector=[0.31] * get_settings().embedding_dimension,
        embedding_provider="test",
        embedding_model="test-model",
        embedding_version="test-v1",
        content_hash="lifecycle-user-hash",
        importance_score=0.8,
        access_count=2,
        metadata_json={},
        scope="user",
        tags=["user"],
        created_at=fresh_timestamp,
        updated_at=fresh_timestamp,
        last_accessed_at=fresh_timestamp,
    )
    db_session.add(stale_session)
    db_session.add(fresh_user)
    db_session.commit()

    response = client.get(
        "/api/v1/deepspace/chats/memory/lifecycle",
        headers=headers,
        params=[("sample_queries", "temporary session note")],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["memory_count"] == 2
    assert payload["stale_count"] == 1
    assert payload["stale_session_count"] == 1
    assert payload["stale_preview_count"] == 1
    assert payload["stale_memory_ids"] == ["lifecycle-stale-memory"]
    assert payload["attention_memories"][0]["key"] == "session_note"
    assert payload["attention_memories"][0]["retention_state"] == "stale"
    assert payload["retention_policy"]["decay_half_life_days"] == 120.0
    assert payload["session_retention_days"] == 7
    assert payload["memory_health_score"] <= 100
    assert payload["retention_risk_count"] >= 1
    assert payload["sample_queries"][0]["matches"] >= 1

    db_session.expire_all()
    memories = asyncio.run(
        MemoryService(db_session).list_all_memories(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
        )
    )
    assert len(memories) == 2


def test_deepspace_memory_evaluation_endpoint_reports_sample_query_recall(
    client,
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "Evaluation Memory Tenant",
        "evaluation-memory@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded)
    service = MemoryService(db_session)

    asyncio.run(
        service.store_fact(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            key="urgent_reply_preference",
            value="For urgent Gmail threads, draft a short reply and ask before sending.",
            scope="user",
            tags=["gmail", "preference"],
            importance_score=0.9,
        )
    )
    asyncio.run(
        service.store_fact(
            tenant_id=str(seeded.tenant_id),
            user_id=str(seeded.user_id),
            key="daily_brief",
            value="Every morning, review the latest AI infrastructure news and summarize it.",
            scope="user",
            tags=["news", "routine"],
            importance_score=0.7,
        )
    )

    response = client.get(
        "/api/v1/deepspace/chats/memory/evaluation",
        headers=headers,
        params=[
            ("sample_queries", "urgent gmail reply"),
            ("sample_queries", "morning news brief"),
        ],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["memory_count"] == 2
    assert payload["embedding_coverage"] == 1.0
    assert payload["duplicate_count"] == 0
    assert payload["stale_session_count"] == 0
    assert payload["memory_health_score"] == 100.0
    assert payload["session_retention_days"] == 7
    assert payload["retention_policy"]["decay_half_life_days"] == 120.0
    assert len(payload["sample_queries"]) == 2
    assert payload["sample_queries"][0]["matches"] >= 1
    assert payload["sample_queries"][0]["top_score"] > 0.0
