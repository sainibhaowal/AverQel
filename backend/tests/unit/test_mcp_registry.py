from app.services.integrations.mcp_registry import get_official_vendor, list_official_vendors


def test_catalog_contains_only_curated_official_vendors() -> None:
    catalog = list_official_vendors()
    assert catalog
    assert {item["vendor"] for item in catalog} >= {"Google", "Notion"}
    assert all("server_url" in item and "docs_url" in item for item in catalog)
    assert not any("smithery" in str(item).lower() for item in catalog)
    assert not any("pipeboard" in str(item).lower() for item in catalog)


def test_unknown_public_registry_id_is_not_installable() -> None:
    assert get_official_vendor("ai.smithery/example") is None
    assert get_official_vendor("co.pipeboard/google-ads-mcp") is None

