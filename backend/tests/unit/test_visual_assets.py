import pytest

from app.core.errors import ApiError
from app.deepspace.api.library import _validate_remote_asset_url, _validated_raster_asset_mime


def test_remote_asset_proxy_rejects_private_hosts() -> None:
    with pytest.raises(Exception, match="Private network"):
        _validate_remote_asset_url("http://127.0.0.1/image.png")


def test_remote_asset_proxy_requires_http_scheme() -> None:
    with pytest.raises(Exception, match=r"HTTP\(S\)"):
        _validate_remote_asset_url("file:///tmp/image.png")


def test_gallery_asset_import_checks_raster_mime_and_file_signature() -> None:
    payload = b"\x89PNG\r\n\x1a\nvalid-png-header"

    assert _validated_raster_asset_mime("image/png; charset=binary", payload) == "image/png"

    with pytest.raises(ApiError, match="matching file type"):
        _validated_raster_asset_mime("image/png", b"<html>not an image</html>")


def test_gallery_asset_import_rejects_active_svg_payloads() -> None:
    with pytest.raises(ApiError, match="supported raster image"):
        _validated_raster_asset_mime("image/svg+xml", b"<svg xmlns='http://www.w3.org/2000/svg'/>")
