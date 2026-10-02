import pytest
from pydantic import ValidationError

from app.documents.schemas.collection_security import (
    CollectionDeviceUpsert,
    CollectionPushSubscriptionRequest,
)


def test_device_identity_is_strictly_bounded() -> None:
    payload = CollectionDeviceUpsert(device_id="browser-123456", label="Laptop")
    assert payload.device_id == "browser-123456"

    with pytest.raises(ValidationError):
        CollectionDeviceUpsert(device_id="bad value")


def test_push_subscription_requires_nontrivial_auth_material() -> None:
    payload = CollectionPushSubscriptionRequest(
        device_id="browser-123456",
        endpoint="https://push.example.test/subscription",
        p256dh="p" * 16,
        auth="a" * 8,
    )
    assert payload.endpoint.startswith("https://")
