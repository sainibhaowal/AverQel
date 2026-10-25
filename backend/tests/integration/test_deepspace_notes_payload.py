import uuid
from datetime import UTC, datetime

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from app.deepspace.repositories.chat import DeepSpaceChatRepository
from tests.conftest import SeededUser


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


def test_deepspace_note_creation_persists_payload(client, seed_user):
    seeded = seed_user(
        "Proactive Tenant",
        "proactive@example.com",
        "password123",
        ("admin",),
    )
    headers = _auth_headers(seeded, roles=("admin",))

    response = client.post(
        "/api/v1/deepspace/chats",
        headers=headers,
        json={
            "title": "Morning Draft",
            "content_html": "<p>Draft body from proactive agents.</p>",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Morning Draft"
    assert payload["content_html"] == "<p>Draft body from proactive agents.</p>"


def test_client_owned_note_updates_and_appends_round_trip_through_same_store(
    client, db_session, seed_user, monkeypatch
):
    from app.deepspace.integrations import client_proxy

    seeded = seed_user(
        "Client Owned Notes Tenant",
        "client-owned-notes@example.com",
        "password123",
        ("user",),
    )
    headers = _auth_headers(seeded, roles=("user",))
    remote_notes: dict[str, dict[str, object]] = {}
    calls: list[str] = []

    def public_note(note: dict[str, object]) -> dict[str, object]:
        return {
            key: note[key]
            for key in ("id", "title", "kind", "created_at", "updated_at", "content_html")
        }

    async def storage_call(_tenant_id, user_id, method, params, **_kwargs):
        calls.append(method)
        assert user_id == str(seeded.user_id)
        if method == "db.chats.create_conversation":
            now = datetime.now(UTC).isoformat()
            note = {
                "id": str(uuid.uuid4()),
                "user_id": str(params["user_id"]),
                "title": params["title"],
                "kind": params["kind"],
                "content_html": params["content_html"],
                "created_at": now,
                "updated_at": now,
            }
            remote_notes[str(note["id"])] = note
            return public_note(note)
        if method == "db.chats.list_conversations":
            return [public_note(note) for note in remote_notes.values()]

        conversation_id = str(params["conversation_id"])
        note = remote_notes.get(conversation_id)
        if note is None or note["user_id"] != user_id or note["kind"] != params["kind"]:
            return None
        if method == "db.chats.get_conversation":
            return public_note(note)
        if method == "db.chats.update_conversation":
            if isinstance(params.get("title"), str):
                note["title"] = params["title"]
            if isinstance(params.get("content_html"), str):
                note["content_html"] = params["content_html"]
        elif method == "db.chats.append_conversation_content":
            existing = str(note.get("content_html") or "").strip()
            addition = str(params["content_html"])
            note["content_html"] = (
                f'{existing}<hr data-averqel-document-separator="true" />{addition}'
                if existing
                else addition
            )
            if note["title"] == "Untitled Note" and isinstance(params.get("title"), str):
                note["title"] = params["title"]
        else:
            raise AssertionError(f"Unexpected client storage method: {method}")
        note["updated_at"] = datetime.now(UTC).isoformat()
        return public_note(note)

    monkeypatch.setattr(client_proxy.client_proxy_registry, "is_storage_connected", lambda *_: True)
    monkeypatch.setattr(client_proxy.client_proxy_registry, "db_proxy_call", storage_call)

    created = client.post(
        "/api/v1/deepspace/chats",
        headers=headers,
        json={"title": "Untitled Note", "content_html": ""},
    )
    assert created.status_code == 200
    conversation_id = created.json()["id"]

    saved = client.patch(
        f"/api/v1/deepspace/chats/{conversation_id}",
        headers=headers,
        json={"content_html": "<p>Durable body.</p>"},
    )
    assert saved.status_code == 200
    assert saved.json()["content_html"] == "<p>Durable body.</p>"

    appended = client.post(
        f"/api/v1/deepspace/chats/{conversation_id}/append-content",
        headers=headers,
        json={"title": "Imported document", "content_html": "<p>Added text.</p>"},
    )
    assert appended.status_code == 200

    reloaded = client.get("/api/v1/deepspace/chats", headers=headers)
    assert reloaded.status_code == 200
    note = next(item for item in reloaded.json()["items"] if item["id"] == conversation_id)
    assert note["title"] == "Imported document"
    assert note["content_html"] == (
        '<p>Durable body.</p><hr data-averqel-document-separator="true" />' "<p>Added text.</p>"
    )
    assert calls == [
        "db.chats.create_conversation",
        "db.chats.update_conversation",
        "db.chats.get_conversation",
        "db.chats.append_conversation_content",
        "db.chats.list_conversations",
    ]

    mirror = DeepSpaceChatRepository(db_session).get_conversation(
        tenant_id=seeded.tenant_id,
        conversation_id=uuid.UUID(conversation_id),
        user_id=seeded.user_id,
        kind="deepspace",
    )
    assert mirror is not None
    assert mirror.title == "Imported document"
    assert mirror.content_html is None


def test_client_owned_note_save_failure_is_not_reported_as_server_saved(
    client, db_session, seed_user, monkeypatch
):
    from app.deepspace.integrations import client_proxy
    from app.deepspace.models.conversation import Conversation

    seeded = seed_user(
        "Client Owned Save Failure Tenant",
        "client-owned-save-failure@example.com",
        "password123",
        ("user",),
    )
    headers = _auth_headers(seeded, roles=("user",))
    created = client.post(
        "/api/v1/deepspace/chats",
        headers=headers,
        json={"title": "Research note", "content_html": "<p>Server copy.</p>"},
    )
    assert created.status_code == 200
    conversation_id = created.json()["id"]

    monkeypatch.setattr(client_proxy.client_proxy_registry, "is_storage_connected", lambda *_: True)

    async def fail_storage(*_args, **_kwargs):
        raise TimeoutError("storage client did not confirm the write")

    monkeypatch.setattr(client_proxy.client_proxy_registry, "db_proxy_call", fail_storage)
    response = client.patch(
        f"/api/v1/deepspace/chats/{conversation_id}",
        headers=headers,
        json={"content_html": "<p>Unconfirmed edit.</p>"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
    from app.platform.database.session import set_db_tenant_context

    set_db_tenant_context(db_session, seeded.tenant_id)
    mirror = db_session.get(Conversation, uuid.UUID(conversation_id))
    assert mirror is not None
    assert mirror.content_html == "<p>Server copy.</p>"


def test_client_owned_note_recovers_newer_legacy_server_copy_then_clears_mirror(
    client, db_session, seed_user, monkeypatch
):
    from app.deepspace.integrations import client_proxy
    from app.deepspace.models.conversation import Conversation
    from app.platform.database.session import set_db_tenant_context

    seeded = seed_user(
        "Client Owned Note Recovery Tenant",
        "client-owned-note-recovery@example.com",
        "password123",
        ("user",),
    )
    headers = _auth_headers(seeded, roles=("user",))
    remote_notes: dict[str, dict[str, object]] = {}

    def public_note(note: dict[str, object]) -> dict[str, object]:
        return {
            key: note[key]
            for key in ("id", "title", "kind", "created_at", "updated_at", "content_html")
        }

    async def storage_call(_tenant_id, user_id, method, params, **_kwargs):
        if method == "db.chats.create_conversation":
            note = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "title": params["title"],
                "kind": params["kind"],
                "content_html": params["content_html"],
                "created_at": "2020-01-01T00:00:00+00:00",
                "updated_at": "2020-01-01T00:00:00+00:00",
            }
            remote_notes[str(note["id"])] = note
            return public_note(note)
        if method == "db.chats.list_conversations":
            return [public_note(note) for note in remote_notes.values()]

        note = remote_notes.get(str(params["conversation_id"]))
        if note is None or note["user_id"] != user_id:
            return None
        if method == "db.chats.get_conversation":
            return public_note(note)
        if method == "db.chats.update_conversation":
            if isinstance(params.get("title"), str):
                note["title"] = params["title"]
            if isinstance(params.get("content_html"), str):
                note["content_html"] = params["content_html"]
            note["updated_at"] = datetime.now(UTC).isoformat()
            return public_note(note)
        if method == "db.chats.append_conversation_content":
            existing = str(note.get("content_html") or "").strip()
            if isinstance(params.get("recovery_content_html"), str):
                observed_updated_at = int(
                    datetime.fromisoformat(str(note["updated_at"])).timestamp() * 1000
                )
                assert params.get("recovery_expected_updated_at") == observed_updated_at
                existing = str(params["recovery_content_html"])
                note["content_html"] = existing
                if isinstance(params.get("recovery_title"), str):
                    note["title"] = params["recovery_title"]
            addition = str(params["content_html"])
            note["content_html"] = (
                f'{existing}<hr data-averqel-document-separator="true" />{addition}'
                if existing
                else addition
            )
            note["updated_at"] = datetime.now(UTC).isoformat()
            return public_note(note)
        raise AssertionError(f"Unexpected client storage method: {method}")

    monkeypatch.setattr(client_proxy.client_proxy_registry, "is_storage_connected", lambda *_: True)
    monkeypatch.setattr(client_proxy.client_proxy_registry, "db_proxy_call", storage_call)
    created = client.post(
        "/api/v1/deepspace/chats",
        headers=headers,
        json={"title": "Research note", "content_html": ""},
    )
    assert created.status_code == 200
    conversation_id = created.json()["id"]
    remote_notes[conversation_id]["content_html"] = "<p>Older client copy.</p>"

    set_db_tenant_context(db_session, seeded.tenant_id)
    mirror = db_session.get(Conversation, uuid.UUID(conversation_id))
    assert mirror is not None
    mirror.content_html = "<p>Last confirmed research text.</p>"
    mirror.updated_at = datetime(2020, 1, 2, tzinfo=UTC)
    db_session.commit()

    loaded = client.get("/api/v1/deepspace/chats", headers=headers)
    assert loaded.status_code == 200
    assert loaded.json()["items"][0]["content_html"] == "<p>Last confirmed research text.</p>"

    saved = client.post(
        f"/api/v1/deepspace/chats/{conversation_id}/append-content",
        headers=headers,
        json={"content_html": "<p>Imported section.</p>"},
    )
    assert saved.status_code == 200
    assert saved.json()["content_html"] == (
        '<p>Last confirmed research text.</p><hr data-averqel-document-separator="true" />'
        "<p>Imported section.</p>"
    )

    db_session.expire_all()
    mirror = db_session.get(Conversation, uuid.UUID(conversation_id))
    assert mirror is not None
    assert mirror.content_html is None


def test_deepspace_document_content_appends_to_active_note(client, seed_user):
    seeded = seed_user(
        "Document Notes Tenant",
        "document-notes@example.com",
        "password123",
        ("user",),
    )
    headers = _auth_headers(seeded, roles=("user",))

    created = client.post(
        "/api/v1/deepspace/chats",
        headers=headers,
        json={"title": "Current Note", "content_html": "<p>Existing note.</p>"},
    )
    assert created.status_code == 200
    conversation_id = created.json()["id"]

    appended = client.post(
        f"/api/v1/deepspace/chats/{conversation_id}/append-content",
        headers=headers,
        json={
            "title": "Extract: course-book.pdf",
            "content_html": "<p>Document selection.</p>",
        },
    )

    assert appended.status_code == 200
    assert appended.json()["title"] == "Current Note"
    assert appended.json()["content_html"] == (
        '<p>Existing note.</p><hr data-averqel-document-separator="true" />'
        "<p>Document selection.</p>"
    )
