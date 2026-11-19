from __future__ import annotations

from conftest import wait_for_status

from paper_review_agent.models import EVALUATION_DIMENSIONS


def test_end_to_end_review_and_evaluation(client):
    payload = {
        "topic": "检索增强生成与引用核验",
        "year_start": 2020,
        "year_end": 2026,
        "keywords": ["RAG", "引用核验"],
        "sources": ["fixture"],
        "candidate_limit": 6,
    }
    response = client.post("/api/v1/tasks", json=payload)
    assert response.status_code == 202, response.text
    task = response.json()
    task_id = task["task_id"]

    task = wait_for_status(client, task_id, {"awaiting_confirmation", "failed"})
    assert task["status"] == "awaiting_confirmation", task.get("error_message")

    assert task["keywords"] == ["RAG", "引用核验"]
    candidates_response = client.get(f"/api/v1/tasks/{task_id}/candidates")
    assert candidates_response.status_code == 200
    candidate_payload = candidates_response.json()
    candidates = candidate_payload["candidates"]
    assert len(candidates) >= 3
    assert candidate_payload["screening_mode"] == "heuristic"
    assert candidate_payload["search_plan"]["mode"] == "heuristic"
    assert all("has_evidence" in paper for paper in candidates)
    selected = [paper["paper_id"] for paper in candidates if paper["has_evidence"]][:3]

    confirm_response = client.post(
        f"/api/v1/tasks/{task_id}/confirm", json={"paper_ids": selected}
    )
    assert confirm_response.status_code == 202, confirm_response.text

    task = wait_for_status(client, task_id, {"completed", "failed"}, timeout=30)
    assert task["status"] == "completed", task.get("error_message")
    assert task["progress"] == 100
    assert task["report_id"]

    report_response = client.get(f"/api/v1/tasks/{task_id}/report")
    assert report_response.status_code == 200, report_response.text
    report = report_response.json()
    assert len(report["sections"]) == 4
    assert report["references"]
    evidence_ids = set(report["evidence"])
    for section in report["sections"]:
        for claim in section["claims"]:
            assert set(claim["evidence_ids"]).issubset(evidence_ids)

    analysis_response = client.get(f"/api/v1/tasks/{task_id}/analysis")
    assert analysis_response.status_code == 200
    analysis = analysis_response.json()
    assert len(analysis["analysis"]["papers"]) == len(selected)
    assert analysis["comparison"]["categories"]

    scores = {key: 4 for key in EVALUATION_DIMENSIONS}
    evaluation_response = client.post(
        f"/api/v1/reports/{report['report_id']}/evaluations",
        json={
            "reviewer_id": "reviewer-01",
            "scale_version": "v1.0",
            "scores": scores,
            "comments": "受控端到端测试",
        },
    )
    assert evaluation_response.status_code == 201, evaluation_response.text
    evaluations = client.get(f"/api/v1/reports/{report['report_id']}/evaluations")
    assert evaluations.status_code == 200
    assert len(evaluations.json()) == 1


def test_invalid_input_returns_field_errors(client):
    response = client.post(
        "/api/v1/tasks",
        json={
            "topic": " ",
            "year_start": 2026,
            "year_end": 2020,
            "sources": [],
            "candidate_limit": 51,
        },
    )
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"] == "invalid_input"
    assert payload["fields"]

def test_cross_session_task_access_is_rejected(client, test_settings):
    from fastapi.testclient import TestClient
    from paper_review_agent.api import create_app

    response = client.post(
        "/api/v1/tasks",
        json={
            "topic": "session isolation test",
            "year_start": 2020,
            "year_end": 2026,
            "sources": ["fixture"],
            "candidate_limit": 3,
        },
    )
    assert response.status_code == 202
    task_id = response.json()["task_id"]
    with TestClient(create_app(test_settings)) as other_session:
        denied = other_session.get(f"/api/v1/tasks/{task_id}")
        assert denied.status_code == 404
        denied_report = other_session.get(f"/api/v1/tasks/{task_id}/report")
        assert denied_report.status_code == 404


def test_failed_task_retry_creates_linked_task(client):
    response = client.post(
        "/api/v1/tasks",
        json={
            "topic": "empty controlled corpus",
            "year_start": 1900,
            "year_end": 1901,
            "sources": ["fixture"],
            "candidate_limit": 2,
        },
    )
    assert response.status_code == 202
    task_id = response.json()["task_id"]
    failed = wait_for_status(client, task_id, {"failed"})
    assert failed["error_stage"] == "retrieval"

    retry = client.post(f"/api/v1/tasks/{task_id}/retry")
    assert retry.status_code == 202, retry.text
    retry_task = retry.json()
    assert retry_task["task_id"] != task_id
    assert retry_task["parent_task_id"] == task_id
