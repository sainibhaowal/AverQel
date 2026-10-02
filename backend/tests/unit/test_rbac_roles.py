from app.auth.rbac import PERMISSIONS_BY_ROLE


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
