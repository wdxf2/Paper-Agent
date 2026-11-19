from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SourceName(str, Enum):
    ARXIV = "arxiv"
    PUBMED = "pubmed"
    FIXTURE = "fixture"
    LOCAL = "local"


class EvidenceScope(str, Enum):
    ABSTRACT = "abstract"
    FULLTEXT = "fulltext"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RETRIEVING = "retrieving"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    ANALYZING = "analyzing"
    WRITING = "writing"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentRole(str, Enum):
    RETRIEVAL = "retrieval"
    ANALYSIS = "analysis"
    COMPARISON = "comparison"
    WRITING = "writing"


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SectionKey(str, Enum):
    BACKGROUND = "background"
    METHODS = "methods"
    EVOLUTION = "evolution"
    OPEN_QUESTIONS = "open_questions"


class ClaimKind(str, Enum):
    EVIDENCE = "evidence"
    LIMITATION = "limitation"


SECTION_TITLES: dict[SectionKey, str] = {
    SectionKey.BACKGROUND: "研究背景",
    SectionKey.METHODS: "主流方法分类",
    SectionKey.EVOLUTION: "技术演进路线",
    SectionKey.OPEN_QUESTIONS: "未解决问题",
}

TASK_STATUS_LABELS: dict[TaskStatus, str] = {
    TaskStatus.PENDING: "待执行",
    TaskStatus.RETRIEVING: "检索中",
    TaskStatus.AWAITING_CONFIRMATION: "等待文献确认",
    TaskStatus.ANALYZING: "分析中",
    TaskStatus.WRITING: "撰写中",
    TaskStatus.VALIDATING: "校验中",
    TaskStatus.COMPLETED: "已完成",
    TaskStatus.FAILED: "已失败",
}

EVALUATION_SCALE_VERSION = "v1.0"
EVALUATION_DIMENSIONS = (
    "topic_relevance",
    "coverage",
    "classification_comparison",
    "citation_support",
    "structure_readability",
)


class TaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(description="自然语言研究主题")
    year_start: int = Field(default=2018, description="起始年份（含）")
    year_end: int = Field(default_factory=lambda: date.today().year)
    keywords: list[str] = Field(default_factory=list, max_length=20)
    sources: list[SourceName] = Field(default_factory=lambda: [SourceName.ARXIV, SourceName.PUBMED])
    candidate_limit: int = Field(default=10)

    @field_validator("topic", mode="before")
    @classmethod
    def strip_topic(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        if not 1 <= len(value) <= 200:
            raise ValueError("研究主题去除首尾空白后应为 1—200 个 Unicode 字符")
        return value

    @field_validator("keywords", mode="before")
    @classmethod
    def strip_keywords(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        return value

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, value: list[str]) -> list[str]:
        unique: list[str] = []
        for item in value:
            if not 1 <= len(item) <= 80:
                raise ValueError("每个关键词应为 1—80 个 Unicode 字符")
            if item not in unique:
                unique.append(item)
        return unique

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, value: list[SourceName]) -> list[SourceName]:
        unique: list[SourceName] = []
        for item in value:
            if item not in unique:
                unique.append(item)
        if not unique:
            raise ValueError("至少选择一个学术数据源")
        return unique

    @model_validator(mode="after")
    def validate_ranges(self) -> "TaskCreateRequest":
        current_year = date.today().year
        errors: list[str] = []
        if self.year_start > self.year_end:
            errors.append("开始年份不得晚于结束年份")
        if self.year_end > current_year:
            errors.append(f"结束年份不得晚于提交当年（{current_year}）")
        if not 1 <= self.candidate_limit <= 50:
            errors.append("候选文献上限应为 1—50")
        if SourceName.LOCAL in self.sources and len(self.sources) > 1:
            errors.append("本地论文模式不能与 arXiv、PubMed 等在线来源同时使用")
        if errors:
            raise ValueError("；".join(errors))
        return self


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: SourceName
    source_id: str
    url: str | None = None


class SearchPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    topic: str
    keywords: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list, max_length=8)
    rationale: str = ""
    mode: Literal["llm", "heuristic"] = "llm"

    @field_validator("queries")
    @classmethod
    def validate_queries(cls, value: list[str]) -> list[str]:
        unique: list[str] = []
        for item in value:
            query = " ".join(item.split()).strip()
            if not query:
                continue
            if len(query) > 600:
                raise ValueError("单个检索式不得超过 600 个字符")
            if query not in unique:
                unique.append(query)
        if not unique:
            raise ValueError("至少需要一个检索式")
        return unique


class CandidateScreening(BaseModel):
    model_config = ConfigDict(extra="ignore")

    paper_id: str
    relevance_score: int = Field(ge=0, le=100)
    decision: Literal["include", "exclude", "borderline"] = "borderline"
    reason: str = ""
    matched_keywords: list[str] = Field(default_factory=list)


class ScreeningResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    selections: list[CandidateScreening] = Field(default_factory=list)
    overall_reason: str = ""


class PaperCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    paper_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int
    abstract: str = ""
    doi: str | None = None
    arxiv_id: str | None = None
    pmid: str | None = None
    url: str | None = None
    peer_reviewed: bool = False
    evidence_scope: EvidenceScope = EvidenceScope.ABSTRACT
    source_records: list[SourceRecord] = Field(default_factory=list)
    is_fixture: bool = False
    suspected_duplicate: bool = False
    duplicate_reason: str | None = None
    evidence_count: int = 0
    has_evidence: bool = False
    llm_relevance_score: int | None = Field(default=None, ge=0, le=100)
    llm_decision: Literal["include", "exclude", "borderline"] | None = None
    llm_reason: str | None = None
    matched_keywords: list[str] = Field(default_factory=list)


class EvidenceFragment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    evidence_id: str
    paper_id: str
    quote: str
    locator: str
    scope: EvidenceScope = EvidenceScope.ABSTRACT


class PaperEvidenceBundle(BaseModel):
    paper: PaperCandidate
    evidence_ids: list[str] = Field(default_factory=list)


class EvidencePack(BaseModel):
    model_config = ConfigDict(extra="ignore")

    topic: str
    year_start: int
    year_end: int
    papers: list[PaperEvidenceBundle] = Field(default_factory=list)
    evidence: list[EvidenceFragment] = Field(default_factory=list)
    coverage_notes: list[str] = Field(default_factory=list)


class PaperAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    paper_id: str
    title: str
    methods: list[str] = Field(default_factory=list)
    experimental_design: str = "未报告或无法判断"
    innovations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_scope: EvidenceScope = EvidenceScope.ABSTRACT


class AnalysisArtifact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    papers: list[PaperAnalysis] = Field(default_factory=list)
    coverage_notes: list[str] = Field(default_factory=list)


class ComparisonPoint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    subject_paper_ids: list[str] = Field(default_factory=list)


class ComparisonArtifact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    categories: list[str] = Field(default_factory=list)
    similarities: list[ComparisonPoint] = Field(default_factory=list)
    differences: list[ComparisonPoint] = Field(default_factory=list)
    evolution: list[ComparisonPoint] = Field(default_factory=list)
    open_questions: list[ComparisonPoint] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class DraftClaim(BaseModel):
    model_config = ConfigDict(extra="ignore")

    claim_id: str
    section: SectionKey
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    subject_paper_ids: list[str] = Field(default_factory=list)
    kind: ClaimKind = ClaimKind.EVIDENCE


class DraftArtifact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    claims: list[DraftClaim] = Field(default_factory=list)
    coverage_notes: list[str] = Field(default_factory=list)


class AgentTaskView(BaseModel):
    agent_task_id: str
    task_id: str
    role: AgentRole
    status: AgentStatus
    input_ref: str | None = None
    output_ref: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class TaskEventView(BaseModel):
    event_id: int
    stage: str
    status: TaskStatus
    message: str
    created_at: datetime


class TaskView(BaseModel):
    task_id: str
    parent_task_id: str | None = None
    topic: str
    year_start: int
    year_end: int
    keywords: list[str] = Field(default_factory=list)
    sources: list[SourceName]
    candidate_limit: int
    status: TaskStatus
    stage_label: str
    progress: int = 0
    error_stage: str | None = None
    error_message: str | None = None
    warnings: list[str] = Field(default_factory=list)
    source_mode: str = "live"
    selected_paper_ids: list[str] = Field(default_factory=list)
    report_id: str | None = None
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None = None
    completed_at: datetime | None = None
    agents: list[AgentTaskView] = Field(default_factory=list)
    events: list[TaskEventView] = Field(default_factory=list)


class CandidateListView(BaseModel):
    task_id: str
    topic: str
    status: TaskStatus
    source_mode: str
    warnings: list[str] = Field(default_factory=list)
    search_plan: SearchPlan | None = None
    screening_mode: str = "heuristic"
    candidates: list[PaperCandidate] = Field(default_factory=list)


class ConfirmSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_ids: list[str] = Field(min_length=1)

    @field_validator("paper_ids")
    @classmethod
    def unique_ids(cls, value: list[str]) -> list[str]:
        unique: list[str] = []
        for item in value:
            if item not in unique:
                unique.append(item)
        if not unique:
            raise ValueError("至少确认一篇具备可用证据的文献")
        return unique


class ReferenceView(BaseModel):
    index: int
    paper_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int
    sources: list[str] = Field(default_factory=list)
    url: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    pmid: str | None = None


class EvidenceView(BaseModel):
    evidence_id: str
    quote: str
    locator: str
    scope: EvidenceScope
    paper: ReferenceView


class ClaimView(BaseModel):
    claim_id: str
    text: str
    kind: ClaimKind
    evidence_ids: list[str] = Field(default_factory=list)
    citation_numbers: list[int] = Field(default_factory=list)
    subject_paper_ids: list[str] = Field(default_factory=list)
    support_score: float | None = None


class ReportSectionView(BaseModel):
    key: SectionKey
    title: str
    claims: list[ClaimView] = Field(default_factory=list)


class ReportView(BaseModel):
    report_id: str
    task_id: str
    title: str
    topic: str
    sections: list[ReportSectionView]
    references: list[ReferenceView]
    evidence: dict[str, EvidenceView]
    coverage_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    semantic_review_required: bool = True
    created_at: datetime


class AnalysisView(BaseModel):
    task_id: str
    analysis: AnalysisArtifact
    comparison: ComparisonArtifact


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_id: str = Field(min_length=1, max_length=100)
    scale_version: str = EVALUATION_SCALE_VERSION
    scores: dict[str, int]
    comments: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_scores(self) -> "EvaluationRequest":
        if self.scale_version != EVALUATION_SCALE_VERSION:
            raise ValueError(f"当前只支持量表版本 {EVALUATION_SCALE_VERSION}")
        expected = set(EVALUATION_DIMENSIONS)
        actual = set(self.scores)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            detail: list[str] = []
            if missing:
                detail.append("缺少维度：" + ", ".join(missing))
            if extra:
                detail.append("未知维度：" + ", ".join(extra))
            raise ValueError("；".join(detail))
        invalid = {key: value for key, value in self.scores.items() if not 1 <= value <= 5}
        if invalid:
            raise ValueError(f"评分应为 1—5 的整数：{invalid}")
        return self


class EvaluationView(BaseModel):
    evaluation_id: str
    report_id: str
    reviewer_id: str
    scale_version: str
    scores: dict[str, int]
    comments: str
    created_at: datetime


class HealthView(BaseModel):
    status: str
    app: str
    crewai_version: str
    engine_mode: str
    llm_mode: str
    database_ready: bool
