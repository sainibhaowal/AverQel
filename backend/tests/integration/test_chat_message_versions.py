import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.dependencies import create_access_token
from app.auth.models.role import Role
from app.auth.models.user import User
from app.auth.models.user_role import UserRole
from app.auth.roles import canonicalize_role_name
from app.auth.security import hash_password
from app.core.config import get_settings
from app.core.ids import generate_uuid7_with_fallback
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.query.repositories.chat import ChatRepository
from tests.conftest import SeededUser, _generate_test_collection_code


def _auth_headers(seeded: SeededUser, *, roles: tuple[str, ...]) -> dict[str, str]:
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


def _add_user_to_existing_tenant(
    *, tenant_id, email: str, password: str, role_name: str
) -> SeededUser:
    session = get_session_factory()()
    try:
        set_db_tenant_context(session, tenant_id)
        user = User(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant_id,
            email=email,
            collection_code=_generate_test_collection_code(),
            password_hash=hash_password(password),
            is_active=True,
        )
        session.add(user)
        session.flush()
        role = session.execute(
            select(Role).where(Role.name == canonicalize_role_name(role_name))
        ).scalar_one()
        session.add(
            UserRole(
                id=generate_uuid7_with_fallback(),
                tenant_id=tenant_id,
                user_id=user.id,
                role_id=role.id,
            )
        )
        session.commit()
        return SeededUser(
            tenant_id=tenant_id,
            user_id=user.id,
            collection_code=user.collection_code,
            email=email,
            password=password,
        )
    finally:
        session.rollback()
        session.close()


def test_message_versions_are_created_and_activated(db_session, seed_user):
    user_data = seed_user(
        "Version Tenant",
        "versions@example.com",
        "password123",
        ("reader",),
    )
    repo = ChatRepository(db_session)
    conversation = repo.create_conversation(
        tenant_id=user_data.tenant_id,
        user_id=user_data.user_id,
        title="Versioned Chat",
    )

    message = repo.add_message(
        tenant_id=user_data.tenant_id,
        conversation_id=conversation.id,
        role="assistant",
        content="Initial answer",
        metadata_json={"trace_id": "trace-1"},
    )

    assert message.active_version is not None
    assert len(message.versions) == 1
    assert message.active_version.content == "Initial answer"

    next_version = repo.create_message_version(
        tenant_id=user_data.tenant_id,
        message_id=message.id,
        content="Regenerated answer",
        metadata_json={"trace_id": "trace-2"},
        source_type="regenerate",
    )
    db_session.commit()

    refreshed = repo.get_message(
        tenant_id=user_data.tenant_id,
        message_id=message.id,
    )
    assert refreshed is not None
    assert refreshed.active_version_id == next_version.id
    assert refreshed.content == "Regenerated answer"
    assert refreshed.metadata_json["trace_id"] == "trace-2"
    assert [item.version_index for item in refreshed.versions] == [1, 2]


def test_deepspace_visual_block_edit_is_revisioned_and_conflict_checked(
    client: TestClient, seed_user
):
    user_data = seed_user(
        "Visual Tenant",
        "visual@example.com",
        "password123",
        ("editor",),
    )
    headers = _auth_headers(user_data, roles=("editor",))
    session = get_session_factory()()
    try:
        set_db_tenant_context(session, user_data.tenant_id)
        repo = ChatRepository(session)
        conversation = repo.create_conversation(
            tenant_id=user_data.tenant_id,
            user_id=user_data.user_id,
            title="Visual Chat",
            kind="deepspace",
        )
        message = repo.add_message(
            tenant_id=user_data.tenant_id,
            conversation_id=conversation.id,
            kind="deepspace",
            role="assistant",
            content=(
                '```chart\n{"title":"Revenue","chart_type":"line",'
                '"series":[{"label":"Q1","value":10},{"label":"Q2","value":20}]}\n```'
            ),
            metadata_json={
                "blocks": [
                    {
                        "id": "chart-1",
                        "type": "chart",
                        "title": "Revenue",
                        "chart_type": "line",
                        "series": [
                            {"label": "Q1", "value": 10},
                            {"label": "Q2", "value": 20},
                        ],
                    }
                ]
            },
        )
        session.commit()
    finally:
        session.rollback()
        session.close()

    updated = client.patch(
        f"/api/v1/deepspace/chats/{conversation.id}/messages/{message.id}/visual-block",
        headers=headers,
        json={
            "block_id": "chart-1",
            "expected_revision": 0,
            "block": {
                "id": "chart-1",
                "type": "chart",
                "source_markdown": '{"title":"Revenue","chart_type":"line","series":[{"label":"Q1","value":10},{"label":"Q2","value":20}]}',
                "title": "Revenue",
                "chart_type": "line",
                "series": [
                    {"label": "Q1", "value": 12},
                    {"label": "Q2", "value": 24},
                ],
            },
        },
    )
    assert updated.status_code == 200
    assert updated.json()["metadata_json"]["visual_blocks"]["chart-1"]["revision"] == 1
    assert '"value": 12' in updated.json()["content"]
    assert '"id": "chart-1"' in updated.json()["content"]

    conflict = client.patch(
        f"/api/v1/deepspace/chats/{conversation.id}/messages/{message.id}/visual-block",
        headers=headers,
        json={
            "block_id": "chart-1",
            "expected_revision": 0,
            "block": {
                "id": "chart-1",
                "type": "chart",
                "title": "Revenue",
                "chart_type": "line",
                "series": [
                    {"label": "Q1", "value": 13},
                    {"label": "Q2", "value": 26},
                ],
            },
        },
    )
    assert conflict.status_code == 409

    note_sync = client.patch(
        f"/api/v1/deepspace/chats/{conversation.id}/visual-block",
        headers=headers,
        json={
            "block_id": "chart-1",
            "expected_revision": 1,
            "block": {
                "id": "chart-1",
                "type": "chart",
                "title": "Revenue",
                "chart_type": "line",
                "series": [{"label": "Q1", "value": 14}, {"label": "Q2", "value": 28}],
                # Artifact and chat edits can advance at different rates; keep
                # the larger visual revision when synchronizing them.
                "revision": 7,
            },
        },
    )
    assert note_sync.status_code == 200
    assert note_sync.json()["metadata_json"]["visual_blocks"]["chart-1"]["revision"] == 7

    artifact = client.post(
        f"/api/v1/deepspace/library/{conversation.id}/visual-artifacts",
        headers=headers,
        json={
            "block_id": "chart-1",
            "filename": "chart-1.visual.json",
            "block": {
                "id": "chart-1",
                "type": "chart",
                "chart_type": "line",
                "series": [{"label": "Q1", "value": 14}, {"label": "Q2", "value": 28}],
                "revision": 7,
            },
        },
    )
    assert artifact.status_code == 200
    assert artifact.json()["version"] == 1

    unchanged_artifact = client.post(
        f"/api/v1/deepspace/library/{conversation.id}/visual-artifacts",
        headers=headers,
        json={
            "block_id": "chart-1",
            "filename": "chart-1.visual.json",
            "expected_version": 1,
            "block": {
                "id": "chart-1",
                "type": "chart",
                "chart_type": "line",
                "series": [{"label": "Q1", "value": 14}, {"label": "Q2", "value": 28}],
                "revision": 7,
            },
        },
    )
    assert unchanged_artifact.status_code == 200
    assert unchanged_artifact.json()["version"] == 1

    artifact_update = client.post(
        f"/api/v1/deepspace/library/{conversation.id}/visual-artifacts",
        headers=headers,
        json={
            "block_id": "chart-1",
            "filename": "chart-1.visual.json",
            "expected_version": 1,
            "block": {
                "id": "chart-1",
                "type": "chart",
                "chart_type": "line",
                "series": [{"label": "Q1", "value": 15}, {"label": "Q2", "value": 30}],
                "revision": 8,
            },
        },
    )
    assert artifact_update.status_code == 200
    assert artifact_update.json()["version"] == 2


def test_latest_turn_pair_tracks_latest_user_and_assistant(db_session, seed_user):
    user_data = seed_user(
        "Turn Tenant",
        "turns@example.com",
        "password123",
        ("reader",),
    )
    repo = ChatRepository(db_session)
    conversation = repo.create_conversation(
        tenant_id=user_data.tenant_id,
        user_id=user_data.user_id,
        title="Turn Chat",
    )

    first_user = repo.add_message(
        tenant_id=user_data.tenant_id,
        conversation_id=conversation.id,
        role="user",
        content="First user prompt",
    )
    repo.add_message(
        tenant_id=user_data.tenant_id,
        conversation_id=conversation.id,
        role="assistant",
        content="First answer",
    )
    latest_user = repo.add_message(
        tenant_id=user_data.tenant_id,
        conversation_id=conversation.id,
        role="user",
        content="Latest user prompt",
    )
    latest_assistant = repo.add_message(
        tenant_id=user_data.tenant_id,
        conversation_id=conversation.id,
        role="assistant",
        content="Latest answer",
    )
    db_session.commit()

    paired_user, paired_assistant = repo.get_latest_turn_pair(
        tenant_id=user_data.tenant_id,
        conversation_id=conversation.id,
    )

    assert paired_user is not None
    assert paired_assistant is not None
    assert paired_user.id != first_user.id
    assert paired_user.id == latest_user.id
    assert paired_assistant.id == latest_assistant.id


def test_delete_message_removes_assistant_and_versions_only(db_session, seed_user):
    user_data = seed_user(
        "Delete Tenant",
        "delete-output@example.com",
        "password123",
        ("reader",),
    )
    repo = ChatRepository(db_session)
    conversation = repo.create_conversation(
        tenant_id=user_data.tenant_id,
        user_id=user_data.user_id,
        title="Delete Output Chat",
    )

    user_message = repo.add_message(
        tenant_id=user_data.tenant_id,
        conversation_id=conversation.id,
        role="user",
        content="Keep this input",
    )
    assistant_message = repo.add_message(
        tenant_id=user_data.tenant_id,
        conversation_id=conversation.id,
        role="assistant",
        content="Delete this output",
    )
    repo.create_message_version(
        tenant_id=user_data.tenant_id,
        message_id=assistant_message.id,
        content="Delete this regenerated output too",
        metadata_json={},
        source_type="regenerate",
    )
    db_session.commit()

    deleted = repo.delete_message(
        tenant_id=user_data.tenant_id,
        conversation_id=conversation.id,
        message_id=assistant_message.id,
    )
    db_session.commit()

    assert deleted is True
    remaining_messages = repo.get_messages(
        tenant_id=user_data.tenant_id,
        conversation_id=conversation.id,
    )
    assert [item.id for item in remaining_messages] == [user_message.id]


def test_chat_and_deepspace_conversations_are_private_between_same_tenant_users(
    client: TestClient,
    seed_user,
) -> None:
    owner = seed_user(
        "Private Chat Tenant",
        "chat-owner@example.com",
        "password123",
        ("editor",),
    )
    other = _add_user_to_existing_tenant(
        tenant_id=owner.tenant_id,
        email="chat-other@example.com",
        password="password123",
        role_name="editor",
    )
    owner_headers = _auth_headers(owner, roles=("editor",))
    other_headers = _auth_headers(other, roles=("editor",))

    session = get_session_factory()()
    try:
        set_db_tenant_context(session, owner.tenant_id)
        repo = ChatRepository(session)
        chat = repo.create_conversation(
            tenant_id=owner.tenant_id,
            user_id=owner.user_id,
            title="Private Chat",
        )
        deep = repo.create_conversation(
            tenant_id=owner.tenant_id,
            user_id=owner.user_id,
            title="Private Note",
            kind="deepspace",
            content_html="<p>private note</p>",
        )
        repo.add_message(
            tenant_id=owner.tenant_id,
            conversation_id=chat.id,
            role="user",
            content="private prompt",
        )
        repo.add_message(
            tenant_id=owner.tenant_id,
            conversation_id=chat.id,
            role="assistant",
            content="private answer",
        )
        repo.add_message(
            tenant_id=owner.tenant_id,
            conversation_id=deep.id,
            kind="deepspace",
            role="user",
            content="private note prompt",
        )
        session.commit()
    finally:
        session.rollback()
        session.close()

    assert (
        client.get(
            f"/api/v1/chats/{chat.id}/messages",
            headers=other_headers,
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/chats/{chat.id}",
            headers=other_headers,
            json={"title": "stolen"},
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/v1/chats/{chat.id}",
            headers=other_headers,
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/deepspace/chats/{deep.id}/messages",
            headers=other_headers,
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/deepspace/export/{deep.id}?format=md",
            headers=other_headers,
        ).status_code
        == 404
    )

    assert (
        client.get(
            f"/api/v1/chats/{chat.id}/messages",
            headers=owner_headers,
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/deepspace/chats/{deep.id}/messages",
            headers=owner_headers,
        ).status_code
        == 200
    )


def test_deepspace_infographic_edit_is_persisted_and_rewritten(client: TestClient, seed_user):
    user_data = seed_user(
        "Infographic Tenant",
        "infographic@example.com",
        "password123",
        ("editor",),
    )
    headers = _auth_headers(user_data, roles=("editor",))
    initial_block = {
        "id": "infographic-1",
        "type": "infographic",
        "title": "Launch steps",
        "layout": "steps",
        "items": [
            {"title": "Research", "icon": "lightbulb"},
            {"title": "Ship", "icon": "zap"},
        ],
        "sources": [{"title": "Launch plan", "url": "https://example.com/plan"}],
    }
    session = get_session_factory()()
    try:
        set_db_tenant_context(session, user_data.tenant_id)
        repo = ChatRepository(session)
        conversation = repo.create_conversation(
            tenant_id=user_data.tenant_id,
            user_id=user_data.user_id,
            title="Visual Chat",
            kind="deepspace",
        )
        message = repo.add_message(
            tenant_id=user_data.tenant_id,
            conversation_id=conversation.id,
            kind="deepspace",
            role="assistant",
            content=f"```infographic\n{json.dumps(initial_block)}\n```",
            metadata_json={"blocks": [initial_block]},
        )
        session.commit()
    finally:
        session.rollback()
        session.close()

    updated = client.patch(
        f"/api/v1/deepspace/chats/{conversation.id}/messages/{message.id}/visual-block",
        headers=headers,
        json={
            "block_id": "infographic-1",
            "expected_revision": 0,
            "block": {
                **initial_block,
                "items": [
                    {"title": "Research", "icon": "lightbulb"},
                    {"title": "Ship safely", "icon": "zap"},
                ],
            },
        },
    )

    assert updated.status_code == 200
    payload = updated.json()
    assert payload["metadata_json"]["visual_blocks"]["infographic-1"]["revision"] == 1
    assert '"title": "Ship safely"' in payload["content"]

    long_date = (
        "Setup: " + "prepare dependencies, configure access, and verify the environment. " * 2
    )
    timeline = {
        **initial_block,
        "layout": "timeline",
        "items": [
            {"title": "Prepare", "date": long_date},
            {"title": "Ship", "date": "Later"},
        ],
    }
    assert len(long_date) > 80
    timeline_update = client.patch(
        f"/api/v1/deepspace/chats/{conversation.id}/messages/{message.id}/visual-block",
        headers=headers,
        json={"block_id": "infographic-1", "expected_revision": 1, "block": timeline},
    )
    assert timeline_update.status_code == 200
    assert (
        timeline_update.json()["metadata_json"]["visual_blocks"]["infographic-1"]["revision"] == 2
    )

    saved_artifact = client.post(
        f"/api/v1/deepspace/library/{conversation.id}/visual-artifacts",
        headers=headers,
        json={"block_id": "infographic-1", "block": {**timeline, "revision": 2}},
    )
    assert saved_artifact.status_code == 200
    assert saved_artifact.json()["version"] == 1
