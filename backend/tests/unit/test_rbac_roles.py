import pytest

from app.auth.rbac import PERMISSIONS_BY_ROLE, resolve_permissions

pytestmark = pytest.mark.unit_no_db


def test_editor_has_advanced_document_organization_permissions() -> None:
    user_permissions = PERMISSIONS_BY_ROLE["user"]
    editor_permissions = PERMISSIONS_BY_ROLE["editor"]

    assert "documents:organization:basic" in user_permissions
    assert "documents:organization:advanced" not in user_permissions
    assert "documents:organization:advanced" in editor_permissions
    assert editor_permissions > user_permissions


def test_user_does_not_receive_admin_permissions() -> None:
    user_permissions = PERMISSIONS_BY_ROLE["user"]
    admin_permissions = PERMISSIONS_BY_ROLE["admin"]

    assert "documents:delete" in user_permissions
    assert "documents:organization:admin" not in user_permissions
    assert "documents:organization:admin" not in PERMISSIONS_BY_ROLE["editor"]
    assert "documents:organization:admin" in admin_permissions
    assert not any(permission.startswith("admin:") for permission in user_permissions)
    assert admin_permissions - user_permissions


def test_legacy_staff_roles_do_not_grant_admin_access_or_assignment() -> None:
    legacy_permissions = resolve_permissions(
        roles=frozenset({"support_manager", "feedback_manager", "collection_moderator"})
    )

    assert not any(permission.startswith("admin:") for permission in legacy_permissions)
    assert "admin:support:read" not in legacy_permissions
    assert "admin:support:write" not in legacy_permissions
    assert "admin:feedback:read" not in legacy_permissions
    assert "admin:feedback:write" not in legacy_permissions
    assert "collections:moderation:read" in legacy_permissions
    assert "collections:moderation:write" in legacy_permissions
    assert "admin:staff_roles:write" not in PERMISSIONS_BY_ROLE["admin"]
