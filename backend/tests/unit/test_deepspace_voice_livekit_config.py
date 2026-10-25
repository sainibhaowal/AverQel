from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit_no_db


def test_livekit_server_pin_supports_current_browser_voice_transport():
    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    livekit = compose["services"]["livekit"]

    assert livekit["image"] == "livekit/livekit-server:v1.13.10"
    assert livekit["ports"] == ["7880:7880", "7881:7881", "7882:7882/udp"]
