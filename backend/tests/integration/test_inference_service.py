from __future__ import annotations

from fastapi.testclient import TestClient

from app.inference import main as inference_main


def test_local_inference_live_health_endpoint() -> None:
    client = TestClient(inference_main.app)

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_local_inference_startup_warms_models_when_enabled(monkeypatch) -> None:
    warmup_calls: list[bool] = []
    monkeypatch.setattr(inference_main.settings, "local_model_warmup_enabled", True)
    monkeypatch.setattr(
        inference_main.runtime,
        "warmup",
        lambda: warmup_calls.append(True),
    )

    with TestClient(inference_main.app):
        pass

    assert warmup_calls == [True]
