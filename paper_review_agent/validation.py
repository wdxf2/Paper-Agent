from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from .models import (
    SECTION_TITLES,
    ClaimKind,
    ClaimView,
    DraftArtifact,
    DraftClaim,
    EvidencePack,
    EvidenceView,
    ReferenceView,
    ReportSectionView,
    ReportView,
    SectionKey,
)
from .text import lexical_support


class ReportValidationError(RuntimeError):
    def __init__(self, issues: list["ValidationIssue"]) -> None:
        self.issues = issues
        super().__init__("；".join(issue.message for issue in issues if issue.fatal))


@dataclass(slots=True)
class ValidationIssue:
    code: str
    claim_id: str | None
    message: str
    fatal: bool = True


@dataclass(slots=True)
class ValidationResult:
    issues: list[ValidationIssue]
    support_scores: dict[str, float]

    @property
    def fatal_issues(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.fatal]

    @property
    def warnings(self) -> list[str]:
        return [issue.message for issue in self.issues if not issue.fatal]


class CitationValidator:
    def __init__(self, support_threshold: float = 0.03) -> None:
        self.support_threshold = support_threshold

    def validate(self, draft: DraftArtifact, pack: EvidencePack) -> ValidationResult:
        issues: list[ValidationIssue] = []
        evidence_map = {fragment.evidence_id: fragment for fragment in pack.evidence}
        selected_papers = {bundle.paper.paper_id: bundle.paper for bundle in pack.papers}
        seen_claim_ids: set[str] = set()
        support_scores: dict[str, float] = {}
        sections_present = {claim.section for claim in draft.claims}
        for section in SectionKey:
            if section not in sections_present:
                issues.append(
                    ValidationIssue(
                        code="missing_section",
                        claim_id=None,
                        message=f"报告缺少必需章节：{SECTION_TITLES[section]}",
                    )
                )

        evidence_claim_count = 0
        for claim in draft.claims:
            if not claim.claim_id or claim.claim_id in seen_claim_ids:
                issues.append(
                    ValidationIssue(
                        code="duplicate_claim_id",
                        claim_id=claim.claim_id,
                        message=f"声明标识重复或为空：{claim.claim_id!r}",
                    )
                )
            seen_claim_ids.add(claim.claim_id)
            if not claim.text.strip():
                issues.append(
                    ValidationIssue(
                        code="empty_claim",
                        claim_id=claim.claim_id,
                        message=f"声明 {claim.claim_id} 正文为空",
                    )
                )
            unknown_subjects = [paper_id for paper_id in claim.subject_paper_ids if paper_id not in selected_papers]
            if unknown_subjects:
                issues.append(
                    ValidationIssue(
                        code="unknown_subject_paper",
                        claim_id=claim.claim_id,
                        message=f"声明 {claim.claim_id} 指向未选择的文献：{', '.join(unknown_subjects)}",
                    )
                )
            if claim.kind == ClaimKind.EVIDENCE:
                evidence_claim_count += 1
                if not claim.evidence_ids:
                    issues.append(
                        ValidationIssue(
                            code="missing_evidence",
                            claim_id=claim.claim_id,
                            message=f"事实性声明 {claim.claim_id} 缺少证据标识",
                        )
                    )
                if claim.section == SectionKey.METHODS and not claim.subject_paper_ids:
                    issues.append(
                        ValidationIssue(
                            code="missing_subject",
                            claim_id=claim.claim_id,
                            message=f"方法章节声明 {claim.claim_id} 未标明对应文献，无法核查归属",
                        )
                    )
                unknown = [evidence_id for evidence_id in claim.evidence_ids if evidence_id not in evidence_map]
                if unknown:
                    issues.append(
                        ValidationIssue(
                            code="dangling_evidence",
                            claim_id=claim.claim_id,
                            message=f"声明 {claim.claim_id} 含悬空证据：{', '.join(unknown)}",
                        )
                    )
                for evidence_id in claim.evidence_ids:
                    fragment = evidence_map.get(evidence_id)
                    if fragment is None:
                        continue
                    if claim.subject_paper_ids and fragment.paper_id not in claim.subject_paper_ids:
                        issues.append(
                            ValidationIssue(
                                code="misattributed_evidence",
                                claim_id=claim.claim_id,
                                message=(
                                    f"声明 {claim.claim_id} 的证据 {evidence_id} 属于文献 "
                                    f"{fragment.paper_id}，不在声明标注的文献集合中"
                                ),
                            )
                        )
                valid_quotes = [
                    evidence_map[evidence_id].quote
                    for evidence_id in claim.evidence_ids
                    if evidence_id in evidence_map
                ]
                score = lexical_support(claim.text, valid_quotes)
                support_scores[claim.claim_id] = round(score, 4)
                if valid_quotes and score < self.support_threshold:
                    issues.append(
                        ValidationIssue(
                            code="low_lexical_support",
                            claim_id=claim.claim_id,
                            message=(
                                f"声明 {claim.claim_id} 与证据的自动词面支持度较低（{score:.2f}），"
                                "需领域评审员抽查语义支持"
                            ),
                            fatal=False,
                        )
                    )

        if evidence_claim_count == 0:
            issues.append(
                ValidationIssue(
                    code="no_evidence_claims",
                    claim_id=None,
                    message="报告没有任何证据支持的正文声明，不允许标记为完成",
                )
            )
        return ValidationResult(issues=issues, support_scores=support_scores)


def repair_draft_once(draft: DraftArtifact, validation: ValidationResult) -> tuple[DraftArtifact, list[str]]:
    bad_claim_ids = {
        issue.claim_id
        for issue in validation.fatal_issues
        if issue.claim_id and issue.code in {
            "missing_evidence", "dangling_evidence", "misattributed_evidence",
            "unknown_subject_paper", "duplicate_claim_id", "missing_subject",
        }
    }
    claims = [claim for claim in draft.claims if claim.claim_id not in bad_claim_ids]
    warnings = [
        f"一次校正移除了 {len(bad_claim_ids)} 条无法通过引用或归属检查的声明"
    ] if bad_claim_ids else []

    present = {claim.section for claim in claims}
    for section in SectionKey:
        if section not in present:
            claims.append(
                DraftClaim(
                    claim_id="repair_" + uuid.uuid4().hex[:8],
                    section=section,
                    text=f"当前材料不足以形成“{SECTION_TITLES[section]}”的可靠正文，需补充证据后重试。",
                    evidence_ids=[],
                    kind=ClaimKind.LIMITATION,
                )
            )
            warnings.append(f"一次校正为缺失章节“{SECTION_TITLES[section]}”加入证据不足说明")
    return draft.model_copy(update={"claims": claims}), warnings


def prepare_report(
    task_id: str,
    pack: EvidencePack,
    draft: DraftArtifact,
    validator: CitationValidator | None = None,
) -> tuple[ReportView, list[str]]:
    validator = validator or CitationValidator()
    first_validation = validator.validate(draft, pack)
    correction_notes: list[str] = []
    if first_validation.fatal_issues:
        draft, correction_notes = repair_draft_once(draft, first_validation)
        second_validation = validator.validate(draft, pack)
        if second_validation.fatal_issues:
            raise ReportValidationError(second_validation.fatal_issues)
        validation = second_validation
    else:
        validation = first_validation

    warnings = list(correction_notes)
    warnings.extend(validation.warnings)
    return (
        build_report_view(
            task_id=task_id,
            pack=pack,
            draft=draft,
            support_scores=validation.support_scores,
            warnings=warnings,
        ),
        warnings,
    )


def build_report_view(
    task_id: str,
    pack: EvidencePack,
    draft: DraftArtifact,
    support_scores: dict[str, float],
    warnings: list[str],
) -> ReportView:
    paper_map = {bundle.paper.paper_id: bundle.paper for bundle in pack.papers}
    evidence_map = {fragment.evidence_id: fragment for fragment in pack.evidence}
    reference_numbers: dict[str, int] = {}
    references: list[ReferenceView] = []
    evidence_views: dict[str, EvidenceView] = {}
    claim_views: dict[SectionKey, list[ClaimView]] = {section: [] for section in SectionKey}

    def reference_for(paper_id: str) -> ReferenceView:
        if paper_id in reference_numbers:
            return next(item for item in references if item.paper_id == paper_id)
        paper = paper_map[paper_id]
        reference = ReferenceView(
            index=len(references) + 1,
            paper_id=paper.paper_id,
            title=paper.title,
            authors=paper.authors,
            year=paper.year,
            sources=[record.source.value for record in paper.source_records],
            url=paper.url,
            doi=paper.doi,
            arxiv_id=paper.arxiv_id,
            pmid=paper.pmid,
        )
        reference_numbers[paper_id] = reference.index
        references.append(reference)
        return reference

    for claim in draft.claims:
        numbers: list[int] = []
        unique_evidence_ids: list[str] = []
        for evidence_id in claim.evidence_ids:
            if evidence_id in unique_evidence_ids or evidence_id not in evidence_map:
                continue
            unique_evidence_ids.append(evidence_id)
            fragment = evidence_map[evidence_id]
            reference = reference_for(fragment.paper_id)
            if reference.index not in numbers:
                numbers.append(reference.index)
            evidence_views[evidence_id] = EvidenceView(
                evidence_id=fragment.evidence_id,
                quote=fragment.quote,
                locator=fragment.locator,
                scope=fragment.scope,
                paper=reference,
            )
        claim_views[claim.section].append(
            ClaimView(
                claim_id=claim.claim_id,
                text=claim.text,
                kind=claim.kind,
                evidence_ids=unique_evidence_ids,
                citation_numbers=numbers,
                subject_paper_ids=claim.subject_paper_ids,
                support_score=support_scores.get(claim.claim_id),
            )
        )

    sections = [
        ReportSectionView(key=section, title=SECTION_TITLES[section], claims=claim_views[section])
        for section in SectionKey
    ]
    coverage_notes = _unique([*pack.coverage_notes, *draft.coverage_notes])
    return ReportView(
        report_id="",
        task_id=task_id,
        title=draft.title,
        topic=pack.topic,
        sections=sections,
        references=references,
        evidence=evidence_views,
        coverage_notes=coverage_notes,
        warnings=_unique(warnings),
        semantic_review_required=True,
        created_at=datetime.now(timezone.utc),
    )


def _unique(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result
