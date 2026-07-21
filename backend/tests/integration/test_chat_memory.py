import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.auth.dependencies import AuthContext
from app.platform.database.session import get_session_factory
from app.query.repositories.chat import ChatRepository
from app.query.services.query_service import QueryService


@pytest.fixture
def db_session():
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def test_conversational_memory_persistence(db_session, settings, seed_user):
    # 0. Seed user and tenant
    user_data = seed_user(
        "Test Tenant", "alice@example.com", "password123", ("reader",)
    )
    tenant_id = user_data.tenant_id
    user_id = user_data.user_id

    repo = ChatRepository(db_session)

    # 1. Create conversation
    conv = repo.create_conversation(
        tenant_id=tenant_id, user_id=user_id, title="Test Chat"
    )
    assert conv.id is not None

    # 2. Add message
    repo.add_message(conversation_id=conv.id, role="user", content="Hello world")
    repo.add_message(conversation_id=conv.id, role="assistant", content="Hi there")

    # 3. Retrieve messages
    messages = repo.get_messages(conversation_id=conv.id)
    assert len(messages) == 2


def test_query_service_session_awareness(db_session, settings, seed_user):
    # 0. Seed user and tenant
    user_data = seed_user(
        "Test Tenant 2", "bob@example.com", "password123", ("reader",)
    )
    auth = AuthContext(
        user_id=user_data.user_id,
        tenant_id=user_data.tenant_id,
        roles={"reader"},
        token_id=str(uuid.uuid4()),
    )

    # Mock retrieval and answer synthesis
    with (
        patch(
            "app.query.services.retrieval_service.RetrievalService.retrieve",
            return_value=[],
        ),
        patch(
            "app.query.services.answer_service.AnswerService.synthesize",
            return_value=MagicMock(
                answer="I remember you said hi.", confidence=0.9, citations=[], usage={}
            ),
        ),
    ):
        service = QueryService(db_session, settings)

        # Run first query
        res1 = service.execute(
            auth=auth,
            query_text="My name is Bob",
            top_k=5,
            filters={},
            document_ids=None,
            created_at_from=None,
            created_at_to=None,
            source_types=None,
            min_extraction_coverage=None,
            max_extraction_coverage=None,
        )
        conv_id = res1.conversation_id
        assert conv_id is not None

        # Run second query in same conversation
        res2 = service.execute(
            auth=auth,
            query_text="What is my name?",
            top_k=5,
            filters={},
            document_ids=None,
            created_at_from=None,
            created_at_to=None,
            source_types=None,
            min_extraction_coverage=None,
            max_extraction_coverage=None,
            conversation_id=conv_id,
        )

        assert res2.conversation_id == conv_id

        # Verify both messages are in DB
        repo = ChatRepository(db_session)
        msgs = repo.get_messages(conversation_id=conv_id)
        assert len(msgs) == 4  # 2 turns
