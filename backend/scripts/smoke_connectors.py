#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

LOGGER = logging.getLogger("smoke_connectors")
DEFAULT_PROVIDERS = (
    "google-drive",
    "gmail",
    "google-calendar",
    "github",
    "slack",
    "notion",
)
CONNECTOR_NAME_PREFIX = "averqel-smoke"
CONNECTOR_MARKER = {"kind": "connector_smoke"}
ACTIVE_STATUSES = {"active"}
HEALTHY_STATUSES = {"healthy", "active"}


ApiClient = Any


@dataclass(slots=True)
class ConnectorSmokeOptions:
    base_url: str
    access_token: str
    providers: tuple[str, ...]
    create_missing: bool = True
    poll_interval_seconds: float = 2.0
    oauth_timeout_seconds: int = 600
    sync_timeout_seconds: int = 600
    dry_run: bool = False


class ConnectorSmokeError(RuntimeError):
    pass


class ConnectorSmokeRunner:
    def __init__(self, client: ApiClient, options: ConnectorSmokeOptions) -> None:
        self.client = client
        self.options = options
        self.headers = {
            "Authorization": f"Bearer {options.access_token}",
            "Content-Type": "application/json",
        }

    def run(self) -> dict[str, Any]:
        integrations = self._fetch_integrations()
        connectors = self._fetch_connectors()
        integration_by_slug = {
            str(item["slug"]): item
            for item in integrations
            if isinstance(item, dict) and item.get("slug")
        }

        results: list[dict[str, Any]] = []
        for provider in self.options.providers:
            results.append(
                self._run_provider(
                    provider=provider,
                    integration=integration_by_slug.get(provider),
                    connectors=connectors,
                )
            )
            connectors = self._fetch_connectors()

        return {
            "status": "success",
            "dry_run": self.options.dry_run,
            "base_url": self.options.base_url,
            "providers": results,
        }

    def _run_provider(
        self,
        *,
        provider: str,
        integration: dict[str, Any] | None,
        connectors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if integration is None:
            raise ConnectorSmokeError(f"Integration not found for provider {provider}")

        oauth_status = integration.get("oauth_status") if isinstance(integration, dict) else None
        if isinstance(oauth_status, dict) and not bool(oauth_status.get("configured")):
            missing = ", ".join(str(item) for item in oauth_status.get("missing") or [])
            raise ConnectorSmokeError(
                f"Provider {provider} is not configured for OAuth on this deployment"
                + (f" (missing: {missing})" if missing else "")
            )

        connector = self._select_or_create_connector(
            provider=provider,
            integration=integration,
            connectors=connectors,
        )
        connector_id = str(connector["id"])
        initial_snapshot = self._normalize_connector(connector)
        LOGGER.info(
            "Running smoke connector flow for provider=%s connector_id=%s connector_name=%s",
            provider,
            connector_id,
            initial_snapshot["name"],
        )

        oauth_start = self._start_oauth(connector_id)
        auth_url = oauth_start.get("authorization_url")
        if oauth_start.get("available") is not True or not auth_url:
            raise ConnectorSmokeError(
                f"OAuth start failed for provider {provider}: {oauth_start.get('message') or 'unknown'}"
            )

        oauth_completed = self._wait_for_connector_state(
            connector_id,
            timeout_seconds=self.options.oauth_timeout_seconds,
            predicate=self._oauth_completed_predicate,
            state_label="OAuth completion",
        )
        if not oauth_completed:
            raise ConnectorSmokeError(
                f"OAuth did not complete for provider {provider} within "
                f"{self.options.oauth_timeout_seconds} seconds"
            )

        before_sync = self._get_connector_snapshot(connector_id)
        sync_response = self._trigger_sync(connector_id)
        if sync_response.get("status") not in {"accepted", "success"}:
            raise ConnectorSmokeError(
                f"Sync request failed for provider {provider}: {sync_response.get('message') or sync_response}"
            )

        sync_completed = self._wait_for_connector_state(
            connector_id,
            timeout_seconds=self.options.sync_timeout_seconds,
            predicate=lambda item: self._sync_completed_predicate(item, before_sync),
            state_label="sync completion",
        )
        if not sync_completed:
            raise ConnectorSmokeError(
                f"Sync did not complete for provider {provider} within "
                f"{self.options.sync_timeout_seconds} seconds"
            )

        final_snapshot = self._get_connector_snapshot(connector_id)
        if final_snapshot.get("status") != "active":
            raise ConnectorSmokeError(
                f"Connector {provider} is not active after sync: {final_snapshot.get('status')}"
            )
        if final_snapshot.get("health_status") not in HEALTHY_STATUSES:
            raise ConnectorSmokeError(
                f"Connector {provider} health is not healthy after sync: "
                f"{final_snapshot.get('health_status')}"
            )
        if final_snapshot.get("circuit_open_until"):
            circuit_open_until = self._parse_dt(str(final_snapshot["circuit_open_until"]))
            if circuit_open_until and circuit_open_until > datetime.now(tz=UTC):
                raise ConnectorSmokeError(
                    f"Connector {provider} still has an open circuit after sync"
                )

        return {
            "provider": provider,
            "integration_id": str(integration["id"]),
            "connector_id": connector_id,
            "connector_name": initial_snapshot["name"],
            "authorization_url": auth_url,
            "oauth_completed": True,
            "sync_completed": True,
            "status": final_snapshot.get("status"),
            "health_status": final_snapshot.get("health_status"),
            "last_sync_at": final_snapshot.get("last_sync_at"),
            "circuit_open_until": final_snapshot.get("circuit_open_until"),
            "last_error": final_snapshot.get("last_error"),
            "error_count": final_snapshot.get("error_count"),
        }

    def _select_or_create_connector(
        self,
        *,
        provider: str,
        integration: dict[str, Any],
        connectors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        integration_id = str(integration["id"])
        connector_name = f"{CONNECTOR_NAME_PREFIX}::{provider}"
        for connector in connectors:
            if str(connector.get("integration_id") or "") != integration_id:
                continue
            if str(connector.get("name") or "") == connector_name:
                return connector

        if not self.options.create_missing:
            raise ConnectorSmokeError(
                f"Connector {connector_name} does not exist and create_missing is disabled"
            )

        payload = {
            "name": connector_name,
            "integration_id": integration_id,
            "collection_id": None,
            "config": {
                **CONNECTOR_MARKER,
                "provider": provider,
                "smoke_runner": True,
            },
            "sync_frequency": "daily",
            "credentials": {},
        }
        response = self.client.post(
            "/api/v1/integrations/connectors", headers=self.headers, json=payload
        )
        self._raise_for_status(response, "create connector")
        connector = response.json()
        if not isinstance(connector, dict):
            raise ConnectorSmokeError(f"Unexpected connector payload for provider {provider}")
        return connector

    def _fetch_integrations(self) -> list[dict[str, Any]]:
        response = self.client.get("/api/v1/integrations", headers=self.headers)
        self._raise_for_status(response, "list integrations")
        payload = response.json()
        if not isinstance(payload, list):
            raise ConnectorSmokeError("Integrations payload must be a list")
        return [item for item in payload if isinstance(item, dict)]

    def _fetch_connectors(self) -> list[dict[str, Any]]:
        response = self.client.get("/api/v1/integrations/connectors", headers=self.headers)
        self._raise_for_status(response, "list connectors")
        payload = response.json()
        if not isinstance(payload, list):
            raise ConnectorSmokeError("Connectors payload must be a list")
        return [item for item in payload if isinstance(item, dict)]

    def _get_connector_snapshot(self, connector_id: str) -> dict[str, Any]:
        for connector in self._fetch_connectors():
            if str(connector.get("id") or "") == connector_id:
                return self._normalize_connector(connector)
        raise ConnectorSmokeError(f"Connector {connector_id} not found")

    def _start_oauth(self, connector_id: str) -> dict[str, Any]:
        response = self.client.post(
            f"/api/v1/integrations/connectors/{connector_id}/oauth/start",
            headers=self.headers,
        )
        self._raise_for_status(response, "start connector OAuth")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ConnectorSmokeError("OAuth start response must be an object")
        return payload

    def _trigger_sync(self, connector_id: str) -> dict[str, Any]:
        response = self.client.post(
            f"/api/v1/integrations/connectors/{connector_id}/sync",
            headers=self.headers,
        )
        self._raise_for_status(response, "trigger connector sync")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ConnectorSmokeError("Sync response must be an object")
        return payload

    def _wait_for_connector_state(
        self,
        connector_id: str,
        *,
        timeout_seconds: int,
        predicate: Any,
        state_label: str,
    ) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() <= deadline:
            connector = self._get_connector_snapshot(connector_id)
            if predicate(connector):
                return True
            time.sleep(self.options.poll_interval_seconds)
        LOGGER.warning("Timed out waiting for %s on connector_id=%s", state_label, connector_id)
        return False

    @staticmethod
    def _parse_dt(value: str) -> datetime | None:
        if not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    @staticmethod
    def _normalize_connector(connector: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(connector.get("id") or ""),
            "name": str(connector.get("name") or ""),
            "integration_id": str(connector.get("integration_id") or ""),
            "status": str(connector.get("status") or "").strip().lower(),
            "health_status": str(connector.get("health_status") or "").strip().lower(),
            "last_sync_at": connector.get("last_sync_at"),
            "circuit_open_until": connector.get("circuit_open_until"),
            "last_error": connector.get("last_error"),
            "error_count": int(connector.get("error_count") or 0),
            "updated_at": connector.get("updated_at"),
            "config": (
                connector.get("config") if isinstance(connector.get("config"), dict) else {}
            ),
        }

    @staticmethod
    def _oauth_completed_predicate(connector: dict[str, Any]) -> bool:
        config_raw = connector.get("config")
        config = config_raw if isinstance(config_raw, dict) else {}
        return (
            connector.get("status") in ACTIVE_STATUSES
            and not connector.get("last_error")
            and str(config.get("auth_mode") or "").strip().lower() == "mcp"
        )

    @staticmethod
    def _sync_completed_predicate(
        connector: dict[str, Any],
        before_sync: dict[str, Any],
    ) -> bool:
        if connector.get("status") != "active":
            return False
        if connector.get("health_status") not in HEALTHY_STATUSES:
            return False
        if connector.get("last_error"):
            return False
        if not connector.get("last_sync_at"):
            return False
        before_sync_value = before_sync.get("last_sync_at")
        if before_sync_value and str(before_sync_value) == str(connector.get("last_sync_at")):
            return False
        circuit_open_until = connector.get("circuit_open_until")
        if circuit_open_until:
            parsed = ConnectorSmokeRunner._parse_dt(str(circuit_open_until))
            if parsed and parsed > datetime.now(tz=UTC):
                return False
        return True

    @staticmethod
    def _raise_for_status(response: httpx.Response, action: str) -> None:
        if response.status_code < 400:
            return
        message = response.text.strip()
        if len(message) > 500:
            message = f"{message[:500]}..."
        raise ConnectorSmokeError(f"Failed to {action}: {response.status_code} {message}")


def _parse_args(argv: list[str]) -> ConnectorSmokeOptions:
    parser = argparse.ArgumentParser(description="Run a connector smoke test across providers.")
    parser.add_argument(
        "--base-url",
        default=os.getenv("AKS_SMOKE_BASE_URL") or "https://averqel.localhost",
    )
    parser.add_argument("--access-token", default=os.getenv("AKS_SMOKE_ACCESS_TOKEN") or "")
    parser.add_argument(
        "--providers",
        default=",".join(DEFAULT_PROVIDERS),
        help="Comma-separated provider slugs to smoke test",
    )
    parser.add_argument(
        "--no-create-missing",
        action="store_true",
        help="Fail instead of creating a missing smoke connector",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=float(os.getenv("AKS_SMOKE_POLL_INTERVAL_SECONDS") or "2"),
    )
    parser.add_argument(
        "--oauth-timeout",
        type=int,
        default=int(os.getenv("AKS_SMOKE_OAUTH_TIMEOUT_SECONDS") or "600"),
    )
    parser.add_argument(
        "--sync-timeout",
        type=int,
        default=int(os.getenv("AKS_SMOKE_SYNC_TIMEOUT_SECONDS") or "600"),
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the plan only.")
    args = parser.parse_args(argv)
    providers = tuple(
        provider.strip() for provider in str(args.providers).split(",") if provider.strip()
    )
    if not providers:
        raise SystemExit("No providers configured for smoke testing")
    if not args.access_token and not args.dry_run:
        raise SystemExit("Missing access token. Set AKS_SMOKE_ACCESS_TOKEN or pass --access-token.")
    return ConnectorSmokeOptions(
        base_url=str(args.base_url).rstrip("/"),
        access_token=str(args.access_token),
        providers=providers,
        create_missing=not bool(args.no_create_missing),
        poll_interval_seconds=float(args.poll_interval),
        oauth_timeout_seconds=int(args.oauth_timeout),
        sync_timeout_seconds=int(args.sync_timeout),
        dry_run=bool(args.dry_run),
    )


def main(argv: list[str] | None = None) -> int:
    options = _parse_args(argv or sys.argv[1:])
    if options.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "base_url": options.base_url,
                    "providers": list(options.providers),
                    "create_missing": options.create_missing,
                    "oauth_timeout_seconds": options.oauth_timeout_seconds,
                    "sync_timeout_seconds": options.sync_timeout_seconds,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    logging.basicConfig(level=os.getenv("AKS_LOG_LEVEL", "INFO"))
    with httpx.Client(base_url=options.base_url, timeout=30.0) as client:
        runner = ConnectorSmokeRunner(client, options)
        payload = runner.run()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
