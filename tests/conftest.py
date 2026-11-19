from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from paper_review_agent.api import create_app
from paper_review_agent.config import Settings
from paper_review_agent.service import ReviewService


@pytest.fixture()
def test_settings(tmp_path):
    return Settings(
        database_path=tmp_path / "paper_review_test.db",
        engine_mode="local",
        offline_fallback=True,
        background_workers=1,
        max_evidence_chars=800,
        rag_top_k=8,
    )


@pytest.fixture()
def client(test_settings):
    service = ReviewService(test_settings)
    app = create_app(test_settings, service)
    with TestClient(app) as test_client:
        yield test_client


def wait_for_status(client: TestClient, task_id: str, expected: set[str], timeout: float = 20.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        response = client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200, response.text
        last = response.json()
        if last["status"] in expected:
            return last
        time.sleep(0.12)
    raise AssertionError(f"Task {task_id} did not reach {expected}; last={last}")
