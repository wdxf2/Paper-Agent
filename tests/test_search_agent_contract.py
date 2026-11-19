from __future__ import annotations

from paper_review_agent.models import (
    CandidateScreening,
    PaperCandidate,
    ScreeningResult,
    SearchPlan,
    SourceName,
    SourceRecord,
    TaskCreateRequest,
)
from paper_review_agent.config import Settings
from paper_review_agent.retrieval import ScreeningPolicy, retriever


def paper(paper_id: str, title: str, year: int = 2024) -> PaperCandidate:
    return PaperCandidate(
        paper_id=paper_id,
        title=title,
        authors=["A"],
        year=year,
        abstract="A controlled abstract.",
        source_records=[SourceRecord(source=SourceName.FIXTURE, source_id=paper_id)],
    )


def test_search_plan_accepts_topic_only_when_keywords_empty():
    request = TaskCreateRequest(topic="retrieval augmented review")
    plan = SearchPlan(topic=request.topic, keywords=request.keywords, queries=[request.topic])
    assert plan.mode == "llm"


def test_screening_policy_orders_include_borderline_and_drops_exclude():
    request = TaskCreateRequest(topic="RAG", keywords=["citation"])
    plan = SearchPlan(topic=request.topic, keywords=request.keywords, queries=[request.topic])
    candidates = [paper("p1", "low"), paper("p2", "high"), paper("p3", "mid")]
    screening = ScreeningResult(
        selections=[
            CandidateScreening(paper_id="p1", relevance_score=55, decision="borderline", reason="borderline"),
            CandidateScreening(paper_id="p2", relevance_score=95, decision="include", reason="relevant"),
            CandidateScreening(paper_id="p3", relevance_score=20, decision="exclude", reason="unrelated"),
        ]
    )
    result = ScreeningPolicy().apply(candidates, screening, limit=2)
    assert [item.paper_id for item in result] == ["p2", "p1"]
    assert result[0].llm_decision == "include"
    assert result[1].llm_decision == "borderline"


class FakeRetriever:
    def plan_search(self, request: TaskCreateRequest) -> SearchPlan:
        return SearchPlan(topic=request.topic, keywords=request.keywords, queries=["focused query"], mode="llm")

    def screen_candidates(self, request: TaskCreateRequest, plan: SearchPlan, candidates: list[PaperCandidate]) -> ScreeningResult:
        return ScreeningResult(
            selections=[
                CandidateScreening(
                    paper_id=candidates[0].paper_id,
                    relevance_score=91,
                    decision="include",
                    reason="matches the supplied topic",
                )
            ]
        )


def test_search_agent_can_plan_and_screen_without_network():
    request = TaskCreateRequest(topic="RAG", keywords=["citation"], sources=[SourceName.FIXTURE])
    service_retriever = retriever(settings=Settings(database_path=":memory:"), search_agent=FakeRetriever())
    plan = service_retriever.plan_search(request)
    assert plan.queries == ["focused query"]
