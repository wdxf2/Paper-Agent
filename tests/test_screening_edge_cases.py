from __future__ import annotations

from paper_review_agent.models import CandidateScreening, PaperCandidate, ScreeningResult, SourceName, SourceRecord
from paper_review_agent.retrieval import ScreeningPolicy


def paper(paper_id: str) -> PaperCandidate:
    return PaperCandidate(
        paper_id=paper_id,
        title=paper_id,
        authors=["A"],
        year=2024,
        abstract="retrieval",
        source_records=[SourceRecord(source=SourceName.FIXTURE, source_id=paper_id)],
    )


def test_excluded_candidates_are_never_used_to_fill_the_requested_limit():
    candidates = [paper("p1"), paper("p2"), paper("p3")]
    result = ScreeningPolicy().apply(
        candidates,
        ScreeningResult(
            selections=[
                CandidateScreening(paper_id="p1", relevance_score=90, decision="include"),
                CandidateScreening(paper_id="p2", relevance_score=30, decision="exclude"),
                CandidateScreening(paper_id="p3", relevance_score=60, decision="borderline"),
            ]
        ),
        limit=3,
    )
    assert [item.paper_id for item in result] == ["p1", "p3"]
    assert all(item.llm_decision != "exclude" for item in result)


def test_unreturned_candidates_are_not_silently_promoted():
    candidates = [paper("p1"), paper("p2")]
    result = ScreeningPolicy().apply(
        candidates,
        ScreeningResult(
            selections=[
                CandidateScreening(paper_id="p1", relevance_score=80, decision="include"),
            ]
        ),
        limit=2,
    )
    assert [item.paper_id for item in result] == ["p1"]
