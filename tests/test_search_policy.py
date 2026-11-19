from __future__ import annotations

from paper_review_agent.models import (
    PaperCandidate,
    ScreeningResult,
    SearchPlan,
    SourceName,
    SourceRecord,
    TaskCreateRequest,
)
from paper_review_agent.retrieval import HeuristicSearchPlanner, ScreeningPolicy


def paper(paper_id: str, title: str, abstract: str = "retrieval augmented generation", year: int = 2024) -> PaperCandidate:
    return PaperCandidate(
        paper_id=paper_id,
        title=title,
        authors=["A"],
        year=year,
        abstract=abstract,
        source_records=[SourceRecord(source=SourceName.FIXTURE, source_id=paper_id)],
    )


def test_heuristic_plan_uses_topic_and_keywords_as_separate_queries():
    request = TaskCreateRequest(topic="RAG literature review", keywords=["citation verification", "evidence grounding"])
    plan = HeuristicSearchPlanner().plan(request)
    assert plan.mode == "heuristic"
    assert plan.queries == ["RAG literature review", "citation verification", "evidence grounding"]
    assert plan.keywords == ["citation verification", "evidence grounding"]


def test_screening_policy_ignores_invented_ids_and_deduplicates_real_ids():
    candidates = [paper("p1", "relevant"), paper("p2", "less relevant")]
    screening = ScreeningResult(
        selections=[
            {"paper_id": "missing", "relevance_score": 100, "decision": "include"},
            {"paper_id": "p2", "relevance_score": 70, "decision": "borderline"},
            {"paper_id": "p1", "relevance_score": 90, "decision": "include"},
            {"paper_id": "p1", "relevance_score": 99, "decision": "include"},
        ]
    )
    result = ScreeningPolicy().apply(candidates, screening, limit=5)
    assert [item.paper_id for item in result] == ["p1", "p2"]
    assert result[0].llm_relevance_score == 90
    assert result[1].llm_decision == "borderline"
