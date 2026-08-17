from app.auth.rbac import PERMISSIONS_BY_ROLE


def test_user_and_editor_have_the_same_workspace_permissions() -> None:
    assert PERMISSIONS_BY_ROLE["user"] == PERMISSIONS_BY_ROLE["editor"]


def test_user_does_not_receive_admin_permissions() -> None:
    user_permissions = PERMISSIONS_BY_ROLE["user"]
    admin_permissions = PERMISSIONS_BY_ROLE["admin"]

    assert "documents:delete" in user_permissions
    assert not any(permission.startswith("admin:") for permission in user_permissions)
    assert admin_permissions - user_permissions
