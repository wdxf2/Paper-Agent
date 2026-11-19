from __future__ import annotations

from pathlib import Path

import pytest

from paper_review_agent.config import Settings
from paper_review_agent.local_papers import LocalLibraryError, LocalPaperLibrary
from paper_review_agent.models import EvidenceScope, SourceName, TaskCreateRequest


def test_local_library_builds_fulltext_evidence_from_text_paper(tmp_path):
    paper_path = tmp_path / "rag_review.txt"
    paper_path.write_text(
        """TITLE: Retrieval-Augmented Generation for Scientific Literature Review
AUTHORS: Alice Example, Bob Example
YEAR: 2025
DOI: 10.1000/example.2025

ABSTRACT: This paper studies retrieval-augmented generation for scientific literature review and citation verification.

1 Introduction
Large language models can draft literature reviews, but unsupported claims remain a major risk.
We motivate evidence-grounded generation and traceable citations.

2 Method
We propose a multi-stage pipeline that retrieves evidence, analyzes papers, compares methods, and verifies citations.
The pipeline preserves source locations and rejects unsupported claims.

3 Experiment
Experiments use a benchmark of scientific papers and compare citation accuracy against baselines.

4 Limitation and Conclusion
The main limitation is reliance on abstract-level evidence in some baselines.
Future work should evaluate full-text evidence and human review.
""",
        encoding="utf-8",
    )

    library = LocalPaperLibrary(Settings(local_paper_dir=tmp_path))
    result = library.load(
        TaskCreateRequest(
            topic="大模型辅助科研文献综述",
            sources=[SourceName.LOCAL],
            candidate_limit=5,
        )
    )

    assert len(result.papers) == 1
    paper = result.papers[0]
    assert paper.title.startswith("Retrieval-Augmented Generation")
    assert paper.year == 2025
    assert paper.doi == "10.1000/example.2025"
    assert paper.evidence_scope == EvidenceScope.FULLTEXT
    assert paper.source_records[0].source == SourceName.LOCAL
    assert result.source_mode == "local"
    assert result.screening_mode == "local"
    assert result.search_plan is None
    assert len(result.evidence) >= 2
    assert all(item.scope == EvidenceScope.FULLTEXT for item in result.evidence)
    assert any("全文" in item.locator for item in result.evidence)


def test_local_library_reports_empty_folder(tmp_path):
    library = LocalPaperLibrary(Settings(local_paper_dir=tmp_path))
    with pytest.raises(LocalLibraryError) as exc_info:
        library.load(
            TaskCreateRequest(
                topic="empty local folder",
                sources=[SourceName.LOCAL],
                candidate_limit=5,
            )
        )
    assert exc_info.value.code == "empty_local_library"


def test_local_source_cannot_mix_with_online_sources():
    with pytest.raises(ValueError):
        TaskCreateRequest(
            topic="mixed sources",
            sources=[SourceName.LOCAL, SourceName.ARXIV],
            candidate_limit=5,
        )


def test_local_library_parses_sample_arxiv_pdfs():
    samples = Path("local_papers/samples")
    if not any(samples.glob("*.pdf")):
        pytest.skip("sample PDFs are not available")
    settings = Settings(
        local_paper_dir=samples,
        local_paper_max_chunks_per_paper=4,
    )
    result = LocalPaperLibrary(settings).load(
        TaskCreateRequest(
            topic="retrieval augmented generation",
            sources=[SourceName.LOCAL],
            candidate_limit=10,
        )
    )

    assert len(result.papers) == 4
    assert all(paper.arxiv_id for paper in result.papers)
    assert all(paper.title != "# Sample papers" for paper in result.papers)
    rag = next(paper for paper in result.papers if paper.arxiv_id == "2005.11401")
    assert rag.title == "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"
    assert rag.year == 2020
    assert len(rag.authors) >= 10

    survey = next(paper for paper in result.papers if paper.arxiv_id == "2312.10997")
    assert survey.title == "Retrieval-Augmented Generation for Large Language Models: A Survey"
    assert survey.year == 2023
    assert len(survey.authors) >= 10
