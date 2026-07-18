"""Synthetic HTTP load and cursor-reconnect checks for an isolated DeepSpace staging stack."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import signal
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from threading import Lock
from typing import Any

import httpx
from sqlalchemy import create_engine, text


@dataclass(frozen=True)
class Identity:
    token: str
    tenant_id: str
    user_id: str


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def request_json(client: httpx.Client, method: str, url: str, *, token: str | None = None, **kwargs: object) -> tuple[httpx.Response, dict[str, object]]:
    headers = dict(kwargs.pop("headers", {}) or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = client.request(method, url, headers=headers, **kwargs)
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text[:1000]}
    return response, payload if isinstance(payload, dict) else {"payload": payload}


def runtime_profile(base_url: str, identity: Identity) -> dict[str, object]:
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        response, payload = request_json(client, "GET", "/api/v1/deepspace/chats/runtime", token=identity.token)
    if response.status_code != 200:
        raise RuntimeError(f"runtime profile failed: {response.status_code} {payload}")
    return payload


def create_identity(base_url: str) -> Identity:
    email = f"durable-load-{uuid.uuid4().hex}@staging.invalid"
    password = "StagingLoadOnly!123456789"
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        registered, register_payload = request_json(
            client,
            "POST",
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        if registered.status_code not in {200, 201}:
            raise RuntimeError(f"registration failed: {registered.status_code} {register_payload}")
        logged_in, login_payload = request_json(
            client,
            "POST",
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        if logged_in.status_code != 200:
            raise RuntimeError(f"login failed: {logged_in.status_code} {login_payload}")
        user = dict(login_payload.get("user") or {})
        return Identity(
            token=str(login_payload["access_token"]),
            tenant_id=str(user["tenant_id"]),
            user_id=str(user["user_id"]),
        )


def create_conversations(base_url: str, identity: Identity, count: int) -> list[str]:
    conversation_ids: list[str] = []
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        for index in range(count):
            response, payload = request_json(
                client,
                "POST",
                "/api/v1/deepspace/chats",
                token=identity.token,
                json={"title": f"Synthetic durable load {index}"},
            )
            if response.status_code not in {200, 201}:
                raise RuntimeError(f"conversation failed: {response.status_code} {payload}")
            conversation_ids.append(str(payload["id"]))
    return conversation_ids


def graph_for(index: int) -> dict[str, object]:
    objective = f"Synthetic staging objective {index}: return deterministic evidence."
    return {
        "nodes": [
            {"node_key": "planner", "node_type": "planner", "prompt": f"Plan safely: {objective}", "priority": 110},
            {"node_key": "main_chat", "node_type": "executor", "prompt": objective, "depends_on": ["planner"], "priority": 100},
            {"node_key": "critic", "node_type": "analysis", "prompt": f"Critique evidence for: {objective}", "depends_on": ["main_chat"], "priority": 90},
            {"node_key": "verification", "node_type": "verifier", "prompt": f"Verify completion evidence for: {objective}", "depends_on": ["critic"], "priority": 80},
        ]
    }


def create_run(base_url: str, identity: Identity, conversation_id: str, index: int) -> dict[str, object]:
    started = time.perf_counter()
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        response, payload = request_json(
            client,
            "POST",
            "/api/v1/deepspace/runs",
            token=identity.token,
            headers={"Idempotency-Key": f"staging-load-{uuid.uuid4().hex}"},
            json={
                "objective": f"Synthetic staging objective {index}: return deterministic evidence.",
                "conversation_id": conversation_id,
                "graph": graph_for(index),
                "execution_contract": {
                    "allow_continuation": False,
                    "require_verifier_before_finish": True,
                    "budget": {
                        "max_turns_per_epoch": 16,
                        "max_tool_calls_per_epoch": 2,
                        "max_parallel_nodes": 4,
                        "max_external_side_effects_per_epoch": 0,
                        "max_cost_usd_per_epoch": 0.25,
                        "max_wall_seconds_per_epoch": 120,
                    },
                },
            },
        )
    return {
        "index": index,
        "run_id": str(payload.get("id") or ""),
        "status_code": response.status_code,
        "payload": payload,
        "latency_ms": (time.perf_counter() - started) * 1000.0,
    }


def wait_for_run(base_url: str, identity: Identity, run_id: str, timeout_seconds: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        while time.monotonic() < deadline:
            response, payload = request_json(client, "GET", f"/api/v1/deepspace/runs/{run_id}", token=identity.token)
            if response.status_code != 200:
                return {"run_id": run_id, "status": "http_error", "payload": payload}
            status = str(payload.get("status") or "")
            if status in {"completed", "failed", "cancelled", "awaiting_approval"}:
                return payload
            time.sleep(1.0)
    return {"run_id": run_id, "status": "timeout"}


def read_sse_sequences(client: httpx.Client, url: str, *, token: str, stop_after: int | None = None) -> list[int]:
    sequences: list[int] = []
    with client.stream("GET", url, headers={"Authorization": f"Bearer {token}"}, timeout=60.0) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("id: "):
                continue
            sequences.append(int(line[4:]))
            if stop_after is not None and len(sequences) >= stop_after:
                break
    return sequences


def list_all_events(client: httpx.Client, base_path: str, *, token: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    cursor = 0
    while True:
        response = client.get(
            base_path,
            params={"after_sequence": cursor, "limit": 250},
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        page = response.json()
        if not isinstance(page, list):
            raise RuntimeError(f"event page was not an array: {page}")
        events.extend(item for item in page if isinstance(item, dict))
        has_more = response.headers.get("X-DeepSpace-Has-More") == "true"
        next_cursor = int(response.headers.get("X-DeepSpace-Next-Sequence", cursor))
        if not has_more or next_cursor <= cursor:
            return events
        cursor = next_cursor


def reconnect_check(base_url: str, identity: Identity, run_id: str) -> dict[str, object]:
    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        all_payload = list_all_events(client, f"/api/v1/deepspace/runs/{run_id}/events", token=identity.token)
        expected = [int(item["sequence"]) for item in all_payload]
        first = read_sse_sequences(client, f"/api/v1/deepspace/runs/{run_id}/stream?after_sequence=0", token=identity.token, stop_after=min(3, len(expected)))
        cursor = first[-1] if first else 0
        second = read_sse_sequences(client, f"/api/v1/deepspace/runs/{run_id}/stream?after_sequence={cursor}", token=identity.token)
        combined = first + second
        return {
            "expected_count": len(expected),
            "received_count": len(combined),
            "first_cursor": cursor,
            "lost_events": max(0, len(expected) - len(combined)),
            "duplicate_events": len(combined) - len(set(combined)),
            "ok": combined == expected and len(set(combined)) == len(combined),
        }


def db_metrics(database_url: str) -> dict[str, object]:
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        result = connection.execute(text("""
            SELECT
              (SELECT count(*) FROM agent_runs) AS runs,
              (SELECT count(*) FROM agent_run_events) AS events,
              (SELECT count(*) FROM agent_run_checkpoints) AS checkpoints,
              (SELECT count(*) FROM agent_tool_invocations) AS tool_invocations,
              (SELECT count(*) FROM agent_run_approvals) AS approvals,
              (SELECT count(*) FROM agent_run_leases) AS run_leases,
              (SELECT count(*) FROM agent_run_node_leases) AS node_leases,
              (SELECT count(*) - count(DISTINCT idempotency_key) FROM agent_tool_invocations) AS duplicate_tool_idempotency_keys,
              (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()) AS db_connections
        """)).mappings().one()
    engine.dispose()
    return dict(result)


def redis_metrics(redis_url: str | None) -> dict[str, object] | None:
    if not redis_url:
        return None
    try:
        import redis

        client = redis.Redis.from_url(redis_url, decode_responses=True)
        info = client.info()
        client.close()
        return {
            "connected_clients": info.get("connected_clients"),
            "used_memory_bytes": info.get("used_memory"),
            "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec"),
            "keyspace_hits": info.get("keyspace_hits"),
            "keyspace_misses": info.get("keyspace_misses"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": type(exc).__name__}


def process_metrics(pids: list[int]) -> dict[str, object]:
    try:
        import psutil

        samples: list[dict[str, object]] = []
        for pid in pids:
            try:
                process = psutil.Process(pid)
                samples.append({"pid": pid, "cpu_percent": process.cpu_percent(interval=0.05), "rss_bytes": process.memory_info().rss})
            except psutil.Error:
                samples.append({"pid": pid, "error": "unavailable"})
        return {"processes": samples}
    except Exception as exc:  # noqa: BLE001
        return {"error": type(exc).__name__}


def approval_probe(base_url: str, identity: Identity, timeout_seconds: float) -> dict[str, object]:
    key = f"staging-approval-{uuid.uuid4().hex}"
    graph = {"nodes": [{"node_key": "approval_probe", "node_type": "approval", "prompt": "Approve the staging recovery probe."}]}
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        response, payload = request_json(
            client,
            "POST",
            "/api/v1/deepspace/runs",
            token=identity.token,
            headers={"Idempotency-Key": key},
            json={
                "objective": "Staging approval pause and resume probe.",
                "graph": graph,
                "execution_contract": {"require_verifier_before_finish": False, "budget": {"max_external_side_effects_per_epoch": 0}},
            },
        )
        if response.status_code not in {200, 201}:
            return {"ok": False, "stage": "create", "status_code": response.status_code, "payload": payload}
        run_id = str(payload.get("id") or "")
        paused = wait_for_run(base_url, identity, run_id, timeout_seconds)
        events = list_all_events(client, f"/api/v1/deepspace/runs/{run_id}/events", token=identity.token)
        approval_id = next(
            str((event.get("payload_json") or {}).get("approval_id"))
            for event in events
            if event.get("event_type") in {"approval_requested", "run_paused_for_approval"}
            and isinstance(event.get("payload_json"), dict)
            and (event.get("payload_json") or {}).get("approval_id")
        ) if any(
            event.get("event_type") in {"approval_requested", "run_paused_for_approval"}
            and isinstance(event.get("payload_json"), dict)
            and (event.get("payload_json") or {}).get("approval_id")
            for event in events
        ) else ""
        if paused.get("status") != "awaiting_approval" or not approval_id:
            return {"ok": False, "run_id": run_id, "paused_status": paused.get("status"), "approval_id": approval_id}
        resolved, resolved_payload = request_json(
            client,
            "POST",
            f"/api/v1/deepspace/runs/{run_id}/approvals/{approval_id}/resolve",
            token=identity.token,
            json={"approved": True, "note": "staging recovery probe"},
        )
        final = wait_for_run(base_url, identity, run_id, timeout_seconds)
        return {
            "ok": resolved.status_code == 200 and final.get("status") == "completed",
            "run_id": run_id,
            "paused_status": paused.get("status"),
            "resolved_status_code": resolved.status_code,
            "resolved": resolved_payload,
            "final_status": final.get("status"),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--count", type=int, default=100, help="Synthetic users/runs; production validation target is 100-500.")
    parser.add_argument("--concurrency", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--redis-url", default=None)
    parser.add_argument("--provider-mode", choices=("real", "mock"), default="real")
    parser.add_argument("--process-pids", default="", help="Comma-separated API/worker PIDs for CPU/RSS samples.")
    parser.add_argument("--kill-worker-pid", type=int, default=None, help="Explicitly terminate this staging worker after run creation.")
    parser.add_argument("--api-restart-command", default=None, help="Explicit staging API restart command, run after creation.")
    parser.add_argument("--skip-approval-probe", action="store_true")
    args = parser.parse_args()

    if not 1 <= args.count <= 500:
        raise SystemExit("--count must be between 1 and 500; use 100-500 for production staging validation")
    if not 1 <= args.concurrency <= args.count:
        raise SystemExit("--concurrency must be between 1 and --count")
    if args.provider_mode == "mock" and args.count >= 50:
        # Mock traffic can validate transport and persistence, but it must be
        # explicitly marked and cannot be mistaken for provider certification.
        print(json.dumps({"warning": "mock provider mode does not certify external provider capacity"}))

    identity = create_identity(args.base_url)
    provider = runtime_profile(args.base_url, identity)
    if args.provider_mode == "real" and str(provider.get("provider_type") or "").lower() in {"mock", "ollama", "vllm", "lmstudio"}:
        raise SystemExit(f"real provider validation requested but runtime reports local/mock provider: {provider}")
    conversation_ids = create_conversations(args.base_url, identity, args.count)
    started = time.perf_counter()
    results: list[dict[str, object]] = []
    lock = Lock()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(create_run, args.base_url, identity, conversation_ids[index], index) for index in range(args.count)]
        for future in as_completed(futures):
            with lock:
                results.append(future.result())

    worker_kill = None
    if args.kill_worker_pid is not None:
        os.kill(args.kill_worker_pid, signal.SIGTERM)
        worker_kill = {"pid": args.kill_worker_pid, "signal": "SIGTERM", "sent": True}
    api_restart = None
    if args.api_restart_command:
        completed_restart = subprocess.run(shlex.split(args.api_restart_command), check=False, capture_output=True, text=True)
        api_restart = {"command": args.api_restart_command, "returncode": completed_restart.returncode, "ok": completed_restart.returncode == 0}

    create_latencies = [float(item["latency_ms"]) for item in results]
    created = [item for item in results if item["status_code"] in {200, 201} and item["run_id"]]
    runs = [str(item["run_id"]) for item in created]
    final_states: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(wait_for_run, args.base_url, identity, run_id, args.timeout) for run_id in runs]
        for future in as_completed(futures):
            final_states.append(future.result())

    completed = [item for item in final_states if item.get("status") == "completed"]
    reconnect = reconnect_check(args.base_url, identity, runs[0]) if runs else {"ok": False, "reason": "no runs"}
    approval = {"skipped": True} if args.skip_approval_probe else approval_probe(args.base_url, identity, min(args.timeout, 120.0))
    if runs:
        with httpx.Client(base_url=args.base_url, timeout=30.0) as client:
            rehydrate_response, rehydrated = request_json(
                client,
                "GET",
                f"/api/v1/deepspace/runs/{runs[0]}/rehydrate",
                token=identity.token,
            )
    else:
        rehydrate_response, rehydrated = None, {}
    summary = {
        "staging": {"base_url": args.base_url, "provider_mode": args.provider_mode, "provider": provider, "isolated_data_required": True},
        "identity": {"tenant_id": identity.tenant_id, "user_id": identity.user_id},
        "requested_runs": args.count,
        "concurrent_create_workers": args.concurrency,
        "create_success_rate": len(created) / args.count if args.count else 0.0,
        "create_latency_ms": {"p50": percentile(create_latencies, 0.50), "p95": percentile(create_latencies, 0.95), "p99": percentile(create_latencies, 0.99), "max": max(create_latencies or [0.0])},
        "final": {"completed": len(completed), "failed": sum(item.get("status") == "failed" for item in final_states), "awaiting_approval": sum(item.get("status") == "awaiting_approval" for item in final_states), "timeouts": sum(item.get("status") == "timeout" for item in final_states)},
        "run_wall_seconds": time.perf_counter() - started,
        "sse_reconnect": reconnect,
        "approval_pause_resume": approval,
        "rehydrate": {"status_code": rehydrate_response.status_code if rehydrate_response else None, "message_count": len(rehydrated.get("messages") or []), "has_run": bool(rehydrated.get("run"))},
        "database": db_metrics(args.database_url) if args.database_url else None,
        "redis": redis_metrics(args.redis_url),
        "processes": process_metrics([int(pid.strip()) for pid in args.process_pids.split(",") if pid.strip()]) if args.process_pids else None,
        "worker_kill": worker_kill,
        "api_restart": api_restart,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not (len(created) == args.count and len(completed) == args.count and bool(reconnect.get("ok")) and bool(approval.get("ok") or approval.get("skipped")) and rehydrate_response is not None and rehydrate_response.status_code == 200):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
