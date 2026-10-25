from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.ingestion.services.ingestion_service import IngestionService
from app.platform.worker.celery_app import celery_app


@pytest.mark.parametrize("filename", ["docker-compose.yml", "docker-compose.prod.yml"])
def test_compose_keeps_light_and_heavy_ingestion_on_bounded_workers(filename: str) -> None:
    compose_path = Path(__file__).resolve().parents[2] / filename
    with compose_path.open(encoding="utf-8") as compose_file:
        services = yaml.safe_load(compose_file)["services"]

    light = services["ingestion-worker"]
    heavy = services["ingestion-heavy-worker"]

    assert light["environment"]["AKS_WORKER_QUEUES"] == "ingestion_light"
    assert light["mem_limit"] == "${AKS_INGESTION_LIGHT_MEMORY_LIMIT:-1g}"
    assert light["cpus"] == "${AKS_INGESTION_LIGHT_CPU_LIMIT:-1.0}"
    assert heavy["environment"]["AKS_WORKER_QUEUES"] == "ingestion_heavy"
    assert heavy["environment"]["AKS_WORKER_CONCURRENCY"] == (
        "${AKS_INGESTION_HEAVY_WORKER_CONCURRENCY:-1}"
    )
    assert heavy["mem_limit"] == "${AKS_INGESTION_HEAVY_MEMORY_LIMIT:-4g}"
    assert heavy["cpus"] == "${AKS_INGESTION_HEAVY_CPU_LIMIT:-2.0}"
    assert heavy["pids_limit"] == "${AKS_INGESTION_HEAVY_PIDS_LIMIT:-256}"


@pytest.mark.parametrize(
    ("filename", "expected_queue"),
    [
        ("annual-report.pdf", "ingestion_heavy"),
        ("scan.tiff", "ingestion_heavy"),
        ("slides.pptx", "ingestion_heavy"),
        ("notes.txt", "ingestion_light"),
        ("data.csv", "ingestion_light"),
    ],
)
def test_document_formats_are_dispatched_to_the_expected_ingestion_queue(
    filename: str, expected_queue: str
) -> None:
    assert IngestionService._choose_ingestion_queue(filename) == expected_queue


def test_ingestion_task_is_routed_to_the_heavy_queue() -> None:
    route = celery_app.amqp.router.route({}, "ingestion.process_job", args=(), kwargs={})

    assert route["queue"].name == "ingestion_heavy"
