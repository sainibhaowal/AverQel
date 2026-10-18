from __future__ import annotations

import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_public_gateways_block_the_unauthenticated_prometheus_route() -> None:
    for filename in ("Caddyfile", "Caddyfile.localprod"):
        config = (BACKEND_ROOT / "ops" / "caddy" / filename).read_text()
        assert re.search(
            r"@metrics\s+path\s+/api/v1/metrics\s+handle @metrics\s+\{\s*respond 403\s*\}",
            config,
        )


def test_api_metrics_port_is_internal_in_production_and_loopback_in_development() -> None:
    production = (BACKEND_ROOT / "docker-compose.prod.yml").read_text()
    production_api = re.search(
        r"^  api:\n(?P<service>.*?)(?=^  frontend:)", production, flags=re.MULTILINE | re.DOTALL
    )
    assert production_api is not None
    assert '    expose:\n      - "1000"' in production_api.group("service")
    assert "    ports:" not in production_api.group("service")

    development = (BACKEND_ROOT / "docker-compose.yml").read_text()
    development_api = re.search(
        r"^  api:\n(?P<service>.*?)(?=^  [a-z][a-z0-9_-]*:|^volumes:)",
        development,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert development_api is not None
    assert '      - "127.0.0.1:1000:1000"' in development_api.group("service")
