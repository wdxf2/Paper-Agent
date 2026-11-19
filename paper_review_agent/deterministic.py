from __future__ import annotations

from collections import Counter

from .models import (
    AnalysisArtifact,
    ClaimKind,
    ComparisonArtifact,
    ComparisonPoint,
    DraftArtifact,
    DraftClaim,
    EvidenceFragment,
    EvidencePack,
    PaperAnalysis,
    SectionKey,
)
from .text import normalize_space, split_sentences


METHOD_HINTS = (
    "propose", "framework", "model", "method", "algorithm", "approach",
    "retrieval", "agent", "pipeline", "提出", "框架", "模型", "方法",
    "算法", "智能体", "检索",
)
EXPERIMENT_HINTS = (
    "experiment", "evaluation", "dataset", "benchmark", "baseline",
    "实验", "评估", "数据集", "基准",
)
INNOVATION_HINTS = (
    "novel", "contribution", "introduce", "improve", "innovative",
    "创新", "贡献", "引入", "改进",
)
LIMITATION_HINTS = (
    "limitation", "future work", "unsolved", "challenge", "risk",
    "局限", "未来工作", "未解决", "挑战", "风险",
)


def build_analysis(pack: EvidencePack) -> AnalysisArtifact:
    evidence_by_paper: dict[str, list[EvidenceFragment]] = {}
    for fragment in pack.evidence:
        evidence_by_paper.setdefault(fragment.paper_id, []).append(fragment)

    analyses: list[PaperAnalysis] = []
    for bundle in pack.papers:
        paper = bundle.paper
        fragments = evidence_by_paper.get(paper.paper_id, [])
        sentences = split_sentences(paper.abstract)
        evidence_ids = [fragment.evidence_id for fragment in fragments[:4]]
        methods = _matching_sentences(sentences, METHOD_HINTS, fallback=1)
        experimental = _first_matching(
            sentences,
            EXPERIMENT_HINTS,
            fallback="未报告（可访问证据仅限摘要，未获得实验设计与数值）",
        )
        innovations = _matching_sentences(sentences, INNOVATION_HINTS, fallback=1)
        limitations = _matching_sentences(sentences, LIMITATION_HINTS, fallback=1)
        if not innovations or innovations == methods:
            innovations = ["摘要未明确报告创新点，需人工查阅原文。"]
        if not limitations or limitations == methods:
            limitations = ["摘要未明确报告局限，需结合全文或作者未来工作进一步判断。"]
        analyses.append(
            PaperAnalysis(
                paper_id=paper.paper_id,
                title=paper.title,
                methods=methods or ["未报告或无法判断"],
                experimental_design=experimental,
                innovations=innovations,
                limitations=limitations,
                evidence_ids=evidence_ids,
                evidence_scope=paper.evidence_scope,
            )
        )
    notes = list(pack.coverage_notes)
    notes.append("单篇分析仅基于当前可定位的摘要证据；未取得全文时不能推断全文实验细节。")
    return AnalysisArtifact(papers=analyses, coverage_notes=notes)


def build_comparison(pack: EvidencePack) -> ComparisonArtifact:
    paper_by_id = {bundle.paper.paper_id: bundle.paper for bundle in pack.papers}
    evidence_by_paper: dict[str, list[str]] = {}
    for fragment in pack.evidence:
        evidence_by_paper.setdefault(fragment.paper_id, []).append(fragment.evidence_id)

    taxonomy = {
        "检索增强生成": ("rag", "retrieval-augmented", "retrieval", "检索增强", "检索"),
        "多智能体协同": ("multi-agent", "agent", "智能体", "协同"),
        "引用与证据核验": ("citation", "evidence", "claim", "引用", "证据", "核验"),
        "评估与基准": ("benchmark", "evaluation", "dataset", "评测", "基准", "数据集"),
        "结构化综述工作流": ("survey", "review", "workflow", "pipeline", "综述", "工作流"),
    }
    category_members: dict[str, list[str]] = {}
    for paper in paper_by_id.values():
        text = (paper.title + " " + paper.abstract).lower()
        for category, keywords in taxonomy.items():
            if any(keyword in text for keyword in keywords):
                category_members.setdefault(category, []).append(paper.paper_id)
    categories = list(category_members) or ["主题相关方法"]

    similarities: list[ComparisonPoint] = []
    for category, members in category_members.items():
        if len(members) < 2:
            continue
        evidence_ids = [item for paper_id in members for item in evidence_by_paper.get(paper_id, [])[:2]]
        similarities.append(
            ComparisonPoint(
                text=f"{len(members)} 篇文献的材料都涉及“{category}”，但实现细节和评测条件仍需按原文核对。",
                evidence_ids=evidence_ids[:6],
                subject_paper_ids=members,
            )
        )
    if not similarities:
        similarities.append(
            ComparisonPoint(
                text="当前摘要证据未显示两项以上可直接归为同一技术类别的稳定共性；不做强行归类。",
                evidence_ids=[],
                subject_paper_ids=[],
            )
        )

    differences: list[ComparisonPoint] = []
    for bundle in pack.papers:
        paper = bundle.paper
        analysis_sentence = _first_matching(
            split_sentences(paper.abstract),
            METHOD_HINTS,
            fallback=_first_sentence(paper.abstract) or "摘要未报告可比较的方法细节。",
        )
        differences.append(
            ComparisonPoint(
                text=f"{paper.title}（{paper.year}）：{analysis_sentence}",
                evidence_ids=evidence_by_paper.get(paper.paper_id, [])[:2],
                subject_paper_ids=[paper.paper_id],
            )
        )

    ordered = sorted(pack.papers, key=lambda bundle: (bundle.paper.year, bundle.paper.title))
    evolution: list[ComparisonPoint] = []
    for bundle in ordered:
        paper = bundle.paper
        evolution.append(
            ComparisonPoint(
                text=(
                    f"{paper.year} 年，{paper.title} 提供了与主题相关的方法材料；"
                    "此处只表示发表顺序，不能仅凭年份证明技术继承关系。"
                ),
                evidence_ids=evidence_by_paper.get(paper.paper_id, [])[:1],
                subject_paper_ids=[paper.paper_id],
            )
        )

    open_questions: list[ComparisonPoint] = []
    for bundle in pack.papers:
        paper = bundle.paper
        limitation = _first_matching(
            split_sentences(paper.abstract),
            LIMITATION_HINTS,
            fallback="摘要未明确报告局限，需人工查阅全文与后续研究。",
        )
        open_questions.append(
            ComparisonPoint(
                text=f"{paper.title}：{limitation}",
                evidence_ids=evidence_by_paper.get(paper.paper_id, [])[:1],
                subject_paper_ids=[paper.paper_id],
            )
        )

    caveats = [
        "当前证据范围以摘要为主：未取得的实验设置、数据集、指标和人工评价不能补造。",
        "不同论文的数据集、指标和评测条件未统一时，不给出直接性能排名。",
        "类别与共性由证据文本和规则辅助归纳，语义支持仍需领域评审员抽查。",
    ]
    return ComparisonArtifact(
        categories=categories,
        similarities=similarities,
        differences=differences,
        evolution=evolution,
        open_questions=open_questions,
        caveats=caveats,
    )


def build_draft(
    pack: EvidencePack,
    rag_fragments: list[EvidenceFragment] | None = None,
) -> DraftArtifact:
    analysis = build_analysis(pack)
    comparison = build_comparison(pack)
    evidence_lookup = {fragment.evidence_id: fragment for fragment in pack.evidence}
    rag_ids = {
        fragment.evidence_id
        for fragment in (rag_fragments or [])
        if fragment.evidence_id in evidence_lookup
    }
    claims: list[DraftClaim] = []
    counter = 0

    def next_claim() -> str:
        nonlocal counter
        counter += 1
        return f"c{counter:03d}"

    source_summary = "、".join(
        sorted(
            {
                record.source.value
                for bundle in pack.papers
                for record in bundle.paper.source_records
            }
        )
    )
    claims.append(
        DraftClaim(
            claim_id=next_claim(),
            section=SectionKey.BACKGROUND,
            text=(
                f"本综述围绕“{pack.topic}”分析 {len(pack.papers)} 篇候选文献，"
                f"检索年份为 {pack.year_start}—{pack.year_end}，来源包括 {source_summary or '受控语料'}。"
            ),
            evidence_ids=[],
            kind=ClaimKind.LIMITATION,
        )
    )
    category_text = "、".join(comparison.categories)
    category_ids = _preferred_ids(
        [fragment.evidence_id for fragment in pack.evidence],
        rag_ids,
        limit=4,
    )
    claims.append(
        DraftClaim(
            claim_id=next_claim(),
            section=SectionKey.BACKGROUND,
            text=f"按当前材料可识别的主要方法类别包括：{category_text}；分类仅依据已定位证据。",
            evidence_ids=category_ids,
            subject_paper_ids=[bundle.paper.paper_id for bundle in pack.papers],
        )
    )

    for paper_analysis in analysis.papers:
        method_text = "；".join(paper_analysis.methods[:2])
        ids = _preferred_ids(paper_analysis.evidence_ids, rag_ids, limit=2)
        claims.append(
            DraftClaim(
                claim_id=next_claim(),
                section=SectionKey.METHODS,
                text=f"{paper_analysis.title}：{method_text}",
                evidence_ids=ids,
                subject_paper_ids=[paper_analysis.paper_id],
            )
        )

    year_text = "、".join(
        str(bundle.paper.year)
        for bundle in sorted(pack.papers, key=lambda item: item.paper.year)
    )
    claims.append(
        DraftClaim(
            claim_id=next_claim(),
            section=SectionKey.EVOLUTION,
            text=(
                f"从发表顺序看，相关研究覆盖 {year_text} 年；"
                "年份先后只表示时间顺序，不能单独证明技术继承。"
            ),
            evidence_ids=_evolution_ids(pack, rag_ids),
            subject_paper_ids=[bundle.paper.paper_id for bundle in pack.papers],
            kind=ClaimKind.EVIDENCE,
        )
    )
    for point in comparison.evolution[: max(1, min(3, len(comparison.evolution)))]:
        claims.append(
            DraftClaim(
                claim_id=next_claim(),
                section=SectionKey.EVOLUTION,
                text=point.text,
                evidence_ids=_preferred_ids(point.evidence_ids, rag_ids, limit=2),
                subject_paper_ids=point.subject_paper_ids,
            )
        )

    for point in comparison.open_questions[: max(2, min(4, len(comparison.open_questions)))]:
        claims.append(
            DraftClaim(
                claim_id=next_claim(),
                section=SectionKey.OPEN_QUESTIONS,
                text=point.text,
                evidence_ids=_preferred_ids(point.evidence_ids, rag_ids, limit=2),
                subject_paper_ids=point.subject_paper_ids,
            )
        )

    claims.append(
        DraftClaim(
            claim_id=next_claim(),
            section=SectionKey.OPEN_QUESTIONS,
            text="当前材料未统一实验条件，尚不能据此给出性能优劣排名或确定性学术结论。",
            evidence_ids=[],
            kind=ClaimKind.LIMITATION,
        )
    )
    notes = list(pack.coverage_notes)
    notes.extend(comparison.caveats)
    notes.append("报告由原型系统生成，事实、分类和比较均需领域评审员复核。")
    return DraftArtifact(
        title=f"{pack.topic}研究综述（证据可追溯版）",
        claims=claims,
        coverage_notes=notes,
    )


def _matching_sentences(sentences: list[str], hints: tuple[str, ...], fallback: int) -> list[str]:
    matches = [
        sentence
        for sentence in sentences
        if any(hint in sentence.lower() for hint in hints)
    ]
    if matches:
        return [normalize_space(item) for item in matches[:2]]
    return [normalize_space(item) for item in sentences[:fallback] if normalize_space(item)]


def _first_matching(sentences: list[str], hints: tuple[str, ...], fallback: str) -> str:
    for sentence in sentences:
        if any(hint in sentence.lower() for hint in hints):
            return normalize_space(sentence)
    return fallback


def _first_sentence(text: str) -> str:
    sentences = split_sentences(text)
    return normalize_space(sentences[0]) if sentences else ""


def _preferred_ids(candidates: list[str], rag_ids: set[str], limit: int) -> list[str]:
    preferred = [evidence_id for evidence_id in candidates if evidence_id in rag_ids]
    combined = preferred + [evidence_id for evidence_id in candidates if evidence_id not in preferred]
    unique: list[str] = []
    for evidence_id in combined:
        if evidence_id and evidence_id not in unique:
            unique.append(evidence_id)
    return unique[:limit]


def _evolution_ids(pack: EvidencePack, rag_ids: set[str]) -> list[str]:
    per_year: Counter[str] = Counter()
    by_paper: dict[str, list[str]] = {}
    for fragment in pack.evidence:
        by_paper.setdefault(fragment.paper_id, []).append(fragment.evidence_id)
    ids: list[str] = []
    for bundle in sorted(pack.papers, key=lambda item: item.paper.year):
        year = str(bundle.paper.year)
        if per_year[year] >= 1:
            continue
        ids.extend(_preferred_ids(by_paper.get(bundle.paper.paper_id, []), rag_ids, limit=1))
        per_year[year] += 1
    return ids[:6]
