from __future__ import annotations

import pytest

from app.core.errors import ApiError
from app.deepspace.api.artifacts import _parse_range
from app.deepspace.services.media_artifacts import DeepSpaceMediaArtifactService


def test_media_artifact_accepts_only_real_media_content_types() -> None:
    assert DeepSpaceMediaArtifactService.kind_for_content_type("image/png") == "image"
    assert DeepSpaceMediaArtifactService.kind_for_content_type("video/mp4") == "video"
    assert DeepSpaceMediaArtifactService.kind_for_content_type("audio/mpeg") == "audio"
    assert DeepSpaceMediaArtifactService.kind_for_content_type("text/html") is None


def test_artifact_range_parser_supports_seek_and_suffix_ranges() -> None:
    assert _parse_range("bytes=10-19", total=100) == (10, 19)
    assert _parse_range("bytes=95-", total=100) == (95, 99)
    assert _parse_range("bytes=-8", total=100) == (92, 99)


def test_artifact_range_parser_rejects_invalid_ranges() -> None:
    with pytest.raises(ApiError) as error:
        _parse_range("bytes=100-101", total=100)

    assert error.value.status_code == 416
