from __future__ import annotations

import pytest

from paper_review_agent.config import Settings
from paper_review_agent.crew import CrewAIReviewRunner
from paper_review_agent.models import (
    EvidenceFragment,
    EvidencePack,
    EvidenceScope,
    PaperCandidate,
    PaperEvidenceBundle,
    SourceName,
    SourceRecord,
)


@pytest.mark.integration
def test_crewai_runner_executes_four_tasks_without_api_key(tmp_path):
    p1 = PaperCandidate(
        paper_id="p1", title="RAG citation review", authors=["A"], year=2024,
        abstract="This framework uses retrieval evidence and checks citation attribution.",
        source_records=[SourceRecord(source=SourceName.FIXTURE, source_id="f1")],
        evidence_scope=EvidenceScope.ABSTRACT,
    )
    p2 = PaperCandidate(
        paper_id="p2", title="Multi-agent literature workflow", authors=["B"], year=2023,
        abstract="A multi-agent workflow splits paper analysis and review writing tasks. A limitation is evaluation scale.",
        source_records=[SourceRecord(source=SourceName.FIXTURE, source_id="f2")],
        evidence_scope=EvidenceScope.ABSTRACT,
    )
    e1 = EvidenceFragment(
        evidence_id="e1", paper_id="p1",
        quote="This framework uses retrieval evidence and checks citation attribution.",
        locator="Abstract, sentence 1",
    )
    e2 = EvidenceFragment(
        evidence_id="e2", paper_id="p2",
        quote="A multi-agent workflow splits paper analysis and review writing tasks.",
        locator="Abstract, sentence 1",
    )
    pack = EvidencePack(
        topic="evidence grounded review", year_start=2020, year_end=2026,
        papers=[PaperEvidenceBundle(paper=p1, evidence_ids=["e1"]), PaperEvidenceBundle(paper=p2, evidence_ids=["e2"])],
        evidence=[e1, e2],
    )
    settings = Settings(
        database_path=tmp_path / "crew.db",
        engine_mode="crewai",
        llm_api_key=None,
        offline_fallback=True,
        rag_top_k=4,
    )
    runner = CrewAIReviewRunner(settings)
    assert runner.llm_mode == "deterministic"
    started: list[str] = []
    finished: list[str] = []
    result = runner.run(
        "task-test", pack,
        on_start=lambda role: started.append(role.value),
        on_finish=lambda role, output: finished.append(role.value),
    )
    assert started == ["retrieval", "analysis", "comparison", "writing"]
    assert finished == ["retrieval", "analysis", "comparison", "writing"]
    assert len(result.analysis.papers) == 2
    assert result.comparison.categories
    assert result.draft.claims
