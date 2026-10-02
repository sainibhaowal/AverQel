from app.system.services.storage_quota import (
    EDITOR_STORAGE_BYTES,
    FREE_STORAGE_BYTES,
    resolve_storage_plan,
)


def test_free_plan_is_the_default_for_normal_roles() -> None:
    plan = resolve_storage_plan(["user"])

    assert plan.id == "free"
    assert plan.storage_limit_bytes == FREE_STORAGE_BYTES
    assert plan.admin_only is False


def test_editor_plan_has_one_gigabyte_storage() -> None:
    plan = resolve_storage_plan(["editor"])

    assert plan.id == "editor"
    assert plan.storage_limit_bytes == EDITOR_STORAGE_BYTES
    assert plan.admin_only is False


def test_admin_role_takes_precedence_and_is_admin_only() -> None:
    plan = resolve_storage_plan(["editor", "admin"])

    assert plan.id == "admin"
    assert plan.storage_limit_bytes == EDITOR_STORAGE_BYTES
    assert plan.admin_only is True


def test_legacy_role_aliases_resolve_safely() -> None:
    assert resolve_storage_plan(["reader"]).id == "free"
    assert resolve_storage_plan(["super_admin"]).id == "admin"
