from __future__ import annotations

from paper_review_agent.models import PaperCandidate, SourceName, SourceRecord
from paper_review_agent.retrieval import deduplicate_and_finalize


def paper(title: str, *, doi=None, arxiv_id=None, pmid=None, author="Alice", year=2024):
    return PaperCandidate(
        paper_id="",
        title=title,
        authors=[author],
        year=year,
        abstract="A controlled abstract with retrieval evidence.",
        doi=doi,
        arxiv_id=arxiv_id,
        pmid=pmid,
        source_records=[
            SourceRecord(source=SourceName.ARXIV, source_id=title, url=None)
        ],
    )


def test_strong_identifier_duplicates_are_merged():
    left = paper("Paper A", doi="https://doi.org/10.1000/ABC")
    right = paper("Paper A duplicate title", doi="doi:10.1000/abc", author="Bob")
    result = deduplicate_and_finalize([left, right])
    assert len(result) == 1
    assert len(result[0].source_records) == 2


def test_arxiv_version_is_normalized():
    left = paper("Paper A", arxiv_id="2401.12345v1")
    right = paper("Paper A other", arxiv_id="2401.12345v3", author="Bob")
    result = deduplicate_and_finalize([left, right])
    assert len(result) == 1


def test_weak_duplicate_is_marked_not_merged():
    left = paper("Same title", year=2024, author="Alice Smith")
    right = paper("Same-title", year=2024, author="alice smith")
    result = deduplicate_and_finalize([left, right])
    assert len(result) == 2
    assert all(item.suspected_duplicate for item in result)
