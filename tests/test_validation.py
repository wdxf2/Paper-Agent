from __future__ import annotations

from paper_review_agent.models import (
    ClaimKind,
    DraftArtifact,
    DraftClaim,
    EvidenceFragment,
    EvidencePack,
    EvidenceScope,
    PaperCandidate,
    PaperEvidenceBundle,
    SectionKey,
    SourceName,
    SourceRecord,
)
from paper_review_agent.rag import EvidenceIndex
from paper_review_agent.validation import CitationValidator, prepare_report


def make_pack():
    p1 = PaperCandidate(
        paper_id="p1", title="RAG review", authors=["A"], year=2024,
        abstract="This framework uses retrieval evidence for citation verification.",
        source_records=[SourceRecord(source=SourceName.FIXTURE, source_id="f1")],
        evidence_scope=EvidenceScope.ABSTRACT,
    )
    p2 = PaperCandidate(
        paper_id="p2", title="Agent review", authors=["B"], year=2023,
        abstract="A multi-agent workflow splits analysis and writing tasks.",
        source_records=[SourceRecord(source=SourceName.FIXTURE, source_id="f2")],
        evidence_scope=EvidenceScope.ABSTRACT,
    )
    e1 = EvidenceFragment(
        evidence_id="e1", paper_id="p1",
        quote="This framework uses retrieval evidence for citation verification.",
        locator="Abstract, sentence 1",
    )
    e2 = EvidenceFragment(
        evidence_id="e2", paper_id="p2",
        quote="A multi-agent workflow splits analysis and writing tasks.",
        locator="Abstract, sentence 1",
    )
    return EvidencePack(
        topic="RAG review", year_start=2020, year_end=2026,
        papers=[PaperEvidenceBundle(paper=p1, evidence_ids=["e1"]), PaperEvidenceBundle(paper=p2, evidence_ids=["e2"])],
        evidence=[e1, e2],
    )


def test_rag_prioritizes_relevant_evidence():
    pack = make_pack()
    hits = EvidenceIndex(pack.evidence).search("retrieval citation evidence", top_k=2)
    assert hits
    assert hits[0].fragment.evidence_id == "e1"


def test_citation_validator_detects_misattribution():
    pack = make_pack()
    draft = DraftArtifact(
        title="Draft",
        claims=[
            DraftClaim(
                claim_id="c1", section=SectionKey.BACKGROUND,
                text="This framework uses retrieval evidence.",
                evidence_ids=["e1"], subject_paper_ids=["p1"],
            ),
            DraftClaim(
                claim_id="c2", section=SectionKey.METHODS,
                text="Agent workflow splits writing tasks.",
                evidence_ids=["e2"], subject_paper_ids=["p1"],
            ),
        ],
    )
    result = CitationValidator().validate(draft, pack)
    assert any(issue.code == "misattributed_evidence" for issue in result.fatal_issues)
    report, warnings = prepare_report("task", pack, draft)
    assert report.sections
    assert any("校正" in warning for warning in warnings)


def test_missing_section_is_repaired_once_or_failed():
    pack = make_pack()
    draft = DraftArtifact(
        title="Draft",
        claims=[
            DraftClaim(
                claim_id="c1", section=SectionKey.BACKGROUND,
                text="This framework uses retrieval evidence.",
                evidence_ids=["e1"], subject_paper_ids=["p1"],
                kind=ClaimKind.EVIDENCE,
            )
        ],
    )
    report, warnings = prepare_report("task", pack, draft)
    assert len(report.sections) == 4
    assert warnings
