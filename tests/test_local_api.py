from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import wait_for_status
from paper_review_agent.api import create_app
from paper_review_agent.config import Settings
from paper_review_agent.service import ReviewService


def write_paper(path, title: str, year: int, abstract: str, method: str):
    path.write_text(
        f"""TITLE: {title}
AUTHORS: Test Author
YEAR: {year}
DOI: 10.1000/{title.lower().replace(' ', '-')}

ABSTRACT: {abstract}

1 Introduction
{abstract}

2 Method
{method}

3 Experiment
The paper reports a benchmark evaluation and compares against baseline systems.

4 Limitation and Conclusion
The limitation is limited human evaluation. Future work should expand the evaluation.
""",
        encoding="utf-8",
    )


def test_local_folder_task_generates_report_without_online_retrieval(tmp_path):
    papers_dir = tmp_path / "local_papers"
    papers_dir.mkdir()
    write_paper(
        papers_dir / "rag.txt",
        "Retrieval Augmented Review Systems",
        2025,
        "This paper studies evidence-grounded literature review.",
        "The proposed method retrieves evidence and verifies citations.",
    )
    write_paper(
        papers_dir / "agents.txt",
        "Multi Agent Literature Analysis",
        2024,
        "This paper studies multi-agent scientific paper analysis.",
        "The proposed method coordinates analysis and comparison agents.",
    )
    settings = Settings(
        database_path=tmp_path / "local_api.db",
        engine_mode="local",
        local_paper_dir=papers_dir,
        background_workers=1,
        rag_top_k=8,
    )
    app = create_app(settings, ReviewService(settings))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tasks",
            json={
                "topic": "本地论文综述",
                "year_start": 2020,
                "year_end": 2026,
                "keywords": ["evidence", "multi-agent"],
                "sources": ["local"],
                "candidate_limit": 5,
            },
        )
        assert response.status_code == 202, response.text
        task_id = response.json()["task_id"]
        task = wait_for_status(client, task_id, {"awaiting_confirmation", "failed"})
        assert task["status"] == "awaiting_confirmation", task.get("error_message")
        assert task["source_mode"] == "local"

        candidates_response = client.get(f"/api/v1/tasks/{task_id}/candidates")
        assert candidates_response.status_code == 200
        payload = candidates_response.json()
        assert payload["source_mode"] == "local"
        assert payload["screening_mode"] == "local"
        assert payload["search_plan"] is None
        assert len(payload["candidates"]) == 2
        assert all(paper["evidence_scope"] == "fulltext" for paper in payload["candidates"])
        assert all(paper["has_evidence"] for paper in payload["candidates"])

        selected = [paper["paper_id"] for paper in payload["candidates"]]
        confirm = client.post(
            f"/api/v1/tasks/{task_id}/confirm", json={"paper_ids": selected}
        )
        assert confirm.status_code == 202, confirm.text
        completed = wait_for_status(client, task_id, {"completed", "failed"}, timeout=30)
        assert completed["status"] == "completed", completed.get("error_message")

        report = client.get(f"/api/v1/tasks/{task_id}/report").json()
        assert len(report["sections"]) == 4
        assert len(report["references"]) == 2
        assert all(
            evidence["scope"] == "fulltext"
            for evidence in report["evidence"].values()
        )
