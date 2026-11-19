from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import httpx

from .config import Settings
from .models import (
    EvidenceFragment,
    EvidenceScope,
    PaperCandidate,
    ScreeningResult,
    SearchPlan,
    SourceName,
    SourceRecord,
    TaskCreateRequest,
)
from .search import HeuristicScreener
from .text import (
    first_author_key,
    normalize_arxiv,
    normalize_doi,
    normalize_pmid,
    normalize_title,
    split_sentences,
    stable_hash,
    truncate,
)


_HEURISTIC_PLAN_WARNING = "未配置模型密钥，本次检索式规划使用主题与关键词规则回退，未调用大模型。"
_HEURISTIC_SCREEN_WARNING = "未配置模型密钥，本次候选筛选使用关键词规则回退，未调用大模型。"


class RetrievalError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SearchAgent(Protocol):
    def plan_search(self, request: TaskCreateRequest) -> SearchPlan: ...

    def screen_candidates(
        self,
        request: TaskCreateRequest,
        plan: SearchPlan,
        candidates: list[PaperCandidate],
    ) -> ScreeningResult: ...


class HeuristicSearchPlanner:
    def plan(self, request: TaskCreateRequest) -> SearchPlan:
        terms = [request.topic, *request.keywords]
        queries: list[str] = []
        for term in terms:
            normalized = " ".join(term.split()).strip()
            if normalized and normalized not in queries:
                queries.append(normalized)
        return SearchPlan(
            topic=request.topic,
            keywords=list(request.keywords),
            queries=queries,
            rationale="未配置大模型时，用主题与用户关键词直接构造检索式。",
            mode="heuristic",
        )

class ScreeningPolicy:
    """Rank valid include/borderline candidates and discard excluded or invented IDs."""

    def apply(
        self,
        candidates: list[PaperCandidate],
        screening: ScreeningResult,
        *,
        limit: int,
    ) -> list[PaperCandidate]:
        by_id = {candidate.paper_id: candidate for candidate in candidates}
        ranked: list[tuple[int, int, int, PaperCandidate]] = []
        seen: set[str] = set()
        decision_order = {"include": 0, "borderline": 1}
        for position, selection in enumerate(screening.selections):
            if selection.paper_id in seen or selection.paper_id not in by_id:
                continue
            if selection.decision == "exclude":
                continue
            seen.add(selection.paper_id)
            candidate = by_id[selection.paper_id].model_copy(
                update={
                    "llm_relevance_score": selection.relevance_score,
                    "llm_decision": selection.decision,
                    "llm_reason": selection.reason,
                    "matched_keywords": selection.matched_keywords,
                }
            )
            ranked.append(
                (decision_order[selection.decision], -selection.relevance_score, position, candidate)
            )
        ranked.sort(key=lambda item: item[:3])
        return [item[3] for item in ranked[:limit]]


@dataclass(slots=True)
class RetrievalResult:
    papers: list[PaperCandidate]
    evidence: list[EvidenceFragment]
    warnings: list[str] = field(default_factory=list)
    source_mode: str = "live"
    search_plan: SearchPlan | None = None
    screening_mode: str = "heuristic"



class SearchProvider(Protocol):
    def search(
        self,
        request: TaskCreateRequest,
        plan: SearchPlan,
        limit: int,
        client: httpx.Client,
    ) -> list[PaperCandidate]: ...


class ArxivProvider:
    def search(
        self,
        request: TaskCreateRequest,
        plan: SearchPlan,
        limit: int,
        client: httpx.Client,
    ) -> list[PaperCandidate]:
        query = build_arxiv_query(plan.queries)
        response = _request_with_retry(
            client,
            "GET",
            "https://export.arxiv.org/api/query",
            params={
                "search_query": query,
                "start": 0,
                "max_results": min(100, max(limit * 2, limit)),
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            },
        )
        root = ET.fromstring(response.text)
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        papers: list[PaperCandidate] = []
        for entry in root.findall("atom:entry", ns):
            title = _xml_text(entry.find("atom:title", ns))
            abstract = _xml_text(entry.find("atom:summary", ns))
            published = _xml_text(entry.find("atom:published", ns))
            year = _extract_year(published)
            if year is None or not (request.year_start <= year <= request.year_end):
                continue
            url = _xml_text(entry.find("atom:id", ns))
            arxiv_match = re.search(r"arxiv\.org/abs/([^/?#]+)", url)
            arxiv_id = normalize_arxiv(arxiv_match.group(1)) if arxiv_match else None
            authors = [
                _xml_text(author.find("atom:name", ns))
                for author in entry.findall("atom:author", ns)
                if _xml_text(author.find("atom:name", ns))
            ]
            doi = normalize_doi(_xml_text(entry.find("arxiv:doi", ns)) or None)
            papers.append(
                PaperCandidate(
                    paper_id="",
                    title=title or "未命名 arXiv 文献",
                    authors=authors,
                    year=year,
                    abstract=abstract,
                    doi=doi,
                    arxiv_id=arxiv_id,
                    url=url or (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else None),
                    peer_reviewed=False,
                    evidence_scope=EvidenceScope.ABSTRACT,
                    source_records=[
                        SourceRecord(
                            source=SourceName.ARXIV,
                            source_id=arxiv_id or url or title,
                            url=url,
                        )
                    ],
                )
            )
        return papers


class PubMedProvider:
    def search(
        self,
        request: TaskCreateRequest,
        plan: SearchPlan,
        limit: int,
        client: httpx.Client,
    ) -> list[PaperCandidate]:
        search_response = _request_with_retry(
            client,
            "GET",
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": build_pubmed_query(plan.queries),
                "retmode": "json",
                "retmax": min(100, max(limit * 2, limit)),
                "sort": "pub date",
                "datetype": "pdat",
                "mindate": str(request.year_start),
                "maxdate": str(request.year_end),
                "tool": "paper_review_agent",
            },
        )
        payload = search_response.json()
        ids = (payload.get("esearchresult") or {}).get("idlist") or []
        if not ids:
            return []
        time.sleep(0.12)
        fetch_response = _request_with_retry(
            client,
            "GET",
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            params={
                "db": "pubmed",
                "id": ",".join(ids[: min(len(ids), limit * 2)]),
                "retmode": "xml",
                "tool": "paper_review_agent",
            },
        )
        root = ET.fromstring(fetch_response.text)
        papers: list[PaperCandidate] = []
        for article in root.findall(".//PubmedArticle"):
            pmid = _xml_text(article.find(".//PMID"))
            if not pmid:
                continue
            title = _xml_text(article.find(".//ArticleTitle")) or "未命名 PubMed 文献"
            abstract_parts = [
                _xml_text(node)
                for node in article.findall(".//AbstractText")
                if _xml_text(node)
            ]
            abstract = " ".join(abstract_parts)
            year = _extract_year(_xml_text(article.find(".//PubDate/Year")))
            if year is None:
                year = _extract_year(_xml_text(article.find(".//PubDate/MedlineDate")))
            if year is None or not (request.year_start <= year <= request.year_end):
                continue
            authors: list[str] = []
            for author in article.findall(".//AuthorList/Author"):
                collective = _xml_text(author.find("CollectiveName"))
                family = _xml_text(author.find("LastName"))
                given = _xml_text(author.find("ForeName"))
                name = collective or " ".join(part for part in (given, family) if part)
                if name:
                    authors.append(name)
            doi = None
            for identifier in article.findall(".//ArticleId"):
                if identifier.attrib.get("IdType") == "doi":
                    doi = normalize_doi(_xml_text(identifier))
                    break
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            papers.append(
                PaperCandidate(
                    paper_id="",
                    title=title,
                    authors=authors,
                    year=year,
                    abstract=abstract,
                    doi=doi,
                    pmid=normalize_pmid(pmid),
                    url=url,
                    peer_reviewed=True,
                    evidence_scope=EvidenceScope.ABSTRACT,
                    source_records=[
                        SourceRecord(source=SourceName.PUBMED, source_id=pmid, url=url)
                    ],
                )
            )
        return papers


class FixtureProvider:
    def __init__(self, path: Path) -> None:
        self.path = path

    def search(
        self,
        request: TaskCreateRequest,
        plan: SearchPlan,
        limit: int,
        client: httpx.Client,
    ) -> list[PaperCandidate]:
        del client, plan
        if not self.path.exists():
            raise RetrievalError("fixture_missing", f"受控测试语料不存在：{self.path}")
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        papers: list[PaperCandidate] = []
        for index, item in enumerate(raw):
            year = int(item.get("year", request.year_end))
            if not (request.year_start <= year <= request.year_end):
                continue
            abstract = str(item.get("abstract", "")).strip()
            papers.append(
                PaperCandidate(
                    paper_id="",
                    title=str(item.get("title", f"受控示例文献 {index + 1}")),
                    authors=list(item.get("authors", [])),
                    year=year,
                    abstract=abstract,
                    doi=normalize_doi(item.get("doi")),
                    arxiv_id=normalize_arxiv(item.get("arxiv_id")),
                    pmid=normalize_pmid(item.get("pmid")),
                    url=item.get("url"),
                    peer_reviewed=bool(item.get("peer_reviewed", False)),
                    evidence_scope=EvidenceScope.ABSTRACT,
                    source_records=[
                        SourceRecord(
                            source=SourceName.FIXTURE,
                            source_id=str(item.get("fixture_id", f"fixture-{index + 1}")),
                            url=item.get("url"),
                        )
                    ],
                    is_fixture=True,
                )
            )
        return papers[:limit]


class LiteratureRetriever:
    """Plan model-assisted searches, fetch candidates, then screen before display."""

    def __init__(
        self,
        settings: Settings,
        fixture_path: Path | None = None,
        *,
        search_agent: SearchAgent | None = None,
    ) -> None:
        self.settings = settings
        self.fixture_path = fixture_path or Path("data/fixtures/papers.json")
        self.search_agent = search_agent
        self.providers: dict[SourceName, SearchProvider] = {
            SourceName.ARXIV: ArxivProvider(),
            SourceName.PUBMED: PubMedProvider(),
            SourceName.FIXTURE: FixtureProvider(self.fixture_path),
        }

    def retrieve(self, request: TaskCreateRequest) -> RetrievalResult:
        warnings: list[str] = []
        plan = self.plan_search(request)
        if plan.mode == "heuristic":
            warnings.append(_HEURISTIC_PLAN_WARNING)
        screening_mode = "llm" if self.search_agent is not None and plan.mode == "llm" else "heuristic"

        collected: list[PaperCandidate] = []
        selected_sources = list(request.sources)
        source_errors: list[str] = []
        source_used: set[SourceName] = set()
        pool_limit = min(
            self.settings.search_pool_max,
            max(self.settings.search_pool_min, request.candidate_limit * self.settings.search_pool_multiplier),
        )

        headers = {"User-Agent": self.settings.user_agent}
        timeout = httpx.Timeout(self.settings.request_timeout_seconds)
        with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as client:
            for source in selected_sources:
                provider = self.providers[source]
                try:
                    found = provider.search(request, plan, pool_limit, client)
                    collected.extend(found)
                    source_used.add(source)
                    if not found:
                        warnings.append(f"{source.value} 未返回符合年份范围的候选文献")
                except Exception as exc:
                    code = getattr(exc, "code", exc.__class__.__name__)
                    message = getattr(exc, "message", str(exc))
                    source_errors.append(f"{source.value}: {code} - {message}")
                    warnings.append(f"{source.value} 检索失败（{code}）：{message}")

        if not collected and self.settings.offline_fallback and SourceName.FIXTURE not in selected_sources:
            warnings.append("外部学术源未产生候选，已切换到受控测试语料；该结果不代表真实检索结论。")
            try:
                with httpx.Client(timeout=timeout) as fallback_client:
                    collected = self.providers[SourceName.FIXTURE].search(
                        request, plan, pool_limit, fallback_client
                    )
                source_used.add(SourceName.FIXTURE)
            except Exception as exc:
                source_errors.append(f"fixture: {exc}")
                warnings.append(f"受控测试语料加载失败：{exc}")

        if not collected:
            detail = "；".join(source_errors) if source_errors else "学术源返回空结果"
            raise RetrievalError("no_candidates", f"未获得候选文献：{detail}")

        deduplicated = deduplicate_and_finalize(collected)
        screening = self.screen_candidates(request, plan, deduplicated)
        if screening is None:
            screening = HeuristicScreener().screen(request.topic, plan.keywords, deduplicated)
            screening_mode = "heuristic"
            if _HEURISTIC_SCREEN_WARNING not in warnings:
                warnings.append(_HEURISTIC_SCREEN_WARNING)
        papers = ScreeningPolicy().apply(deduplicated, screening, limit=request.candidate_limit)
        if not papers:
            raise RetrievalError(
                "no_relevant_candidates",
                "模型筛选后没有达到相关性要求的候选文献；未用不相关文献补足数量。",
            )
        if len(papers) < request.candidate_limit:
            warnings.append(
                f"模型筛选后仅保留 {len(papers)} 篇合适候选，少于请求上限 {request.candidate_limit} 篇；"
                "系统没有用排除项补足数量。"
            )

        evidence = build_evidence(papers, self.settings.max_evidence_chars)
        evidence_counts: dict[str, int] = {}
        for fragment in evidence:
            evidence_counts[fragment.paper_id] = evidence_counts.get(fragment.paper_id, 0) + 1
        for paper in papers:
            paper.evidence_count = evidence_counts.get(paper.paper_id, 0)
            paper.has_evidence = paper.evidence_count > 0

        if source_used == {SourceName.FIXTURE}:
            source_mode = "demo"
            warnings.append("当前使用受控测试语料，仅用于流程验收，不应据此形成真实学术结论。")
        elif source_errors:
            source_mode = "mixed"
        else:
            source_mode = "live"

        return RetrievalResult(
            papers=papers,
            evidence=evidence,
            warnings=warnings,
            source_mode=source_mode,
            search_plan=plan,
            screening_mode=screening_mode,
        )

    def plan_search(self, request: TaskCreateRequest) -> SearchPlan:
        if self.search_agent is not None:
            try:
                plan = self.search_agent.plan_search(request)
                if plan.mode == "llm" and plan.queries:
                    return plan
            except Exception as exc:
                raise RetrievalError("search_planning_failed", f"检索式规划失败：{exc}") from exc
        return HeuristicSearchPlanner().plan(request)

    def screen_candidates(
        self,
        request: TaskCreateRequest,
        plan: SearchPlan,
        candidates: list[PaperCandidate],
    ) -> ScreeningResult | None:
        if self.search_agent is None or plan.mode != "llm":
            return None
        try:
            return self.search_agent.screen_candidates(request, plan, candidates)
        except Exception as exc:
            raise RetrievalError("candidate_screening_failed", f"候选筛选失败：{exc}") from exc


_ARXIV_FIELDS = {
    "all", "ti", "abs", "au", "cat", "co", "jr", "id", "rni", "rn", "doi",
}
_QUERY_OPERATORS = {"AND", "OR", "ANDNOT"}
_QUERY_TOKEN_RE = re.compile(
    r'(?:[A-Za-z]+:)?(?:"[^"]*"|[^\s()]+)|[()]'
)


def build_arxiv_query(queries: list[str]) -> str:
    expressions: list[tuple[str, bool]] = []
    for query in queries:
        normalized = _sanitize_expression(query)
        if not normalized:
            continue
        complex_query = _is_complex_query(normalized)
        rendered = _render_query_expression(normalized, arxiv=True)
        expressions.append((rendered, complex_query))
    return _join_query_expressions(expressions)


def build_pubmed_query(queries: list[str]) -> str:
    expressions: list[tuple[str, bool]] = []
    for query in queries:
        normalized = _sanitize_expression(query)
        if not normalized:
            continue
        complex_query = _is_complex_query(normalized)
        rendered = _render_query_expression(normalized, arxiv=False)
        expressions.append((rendered, complex_query))
    return _join_query_expressions(expressions)


def _join_query_expressions(expressions: list[tuple[str, bool]]) -> str:
    if not expressions:
        return ""
    if len(expressions) == 1 and not expressions[0][1]:
        return expressions[0][0]
    return " OR ".join(f"({rendered})" for rendered, _ in expressions)


def _render_query_expression(query: str, *, arxiv: bool) -> str:
    if not _is_complex_query(query):
        term = _format_query_term(query, arxiv=arxiv)
        return term

    tokens = _QUERY_TOKEN_RE.findall(query)
    parts: list[str] = []
    pending: list[str] = []

    def flush_pending() -> None:
        if not pending:
            return
        term = " ".join(pending).strip()
        pending.clear()
        if term:
            parts.append(_format_query_term(term, arxiv=arxiv))

    for token in tokens:
        if token == "(" or token == ")":
            flush_pending()
            parts.append(token)
        elif token.upper() in _QUERY_OPERATORS:
            flush_pending()
            parts.append(token.upper())
        else:
            pending.append(token)
    flush_pending()
    rendered = " ".join(parts)
    rendered = re.sub(r"\(\s+", "(", rendered)
    rendered = re.sub(r"\s+\)", ")", rendered)
    return rendered


def _is_complex_query(query: str) -> bool:
    return bool(
        re.search(r"\b(?:AND|OR|ANDNOT)\b|[()]|\b(?:all|ti|abs|au|cat|co|jr|id|rni|rn|doi):", query, re.I)
    )


def _format_query_term(term: str, *, arxiv: bool) -> str:
    value = term.strip()
    prefix_match = re.match(r"^([A-Za-z]+):(.*)$", value)
    if prefix_match:
        prefix = prefix_match.group(1).lower()
        value = prefix_match.group(2).strip()
        if arxiv and prefix in _ARXIV_FIELDS:
            return f"{prefix}:{_quote_multiword(value)}"
    value = _quote_multiword(value)
    return f"all:{value}" if arxiv else value


def _quote_multiword(value: str) -> str:
    value = value.strip()
    if not value:
        return '""'
    if value.startswith('"') and value.endswith('"'):
        return value
    if " " in value:
        return f'"{value}"'
    return value


def _sanitize_expression(value: str) -> str:
    cleaned = "".join(character for character in value if character.isprintable())
    cleaned = re.sub(r"[^0-9A-Za-z\u3400-\u9fff\s():_\-.\"]", " ", cleaned)
    return " ".join(cleaned.split()).strip()


def _sanitize_query(value: str) -> str:
    cleaned = "".join(character for character in value if character.isprintable())
    return " ".join(cleaned.replace('"', " ").split()).strip()


def deduplicate_and_finalize(papers: list[PaperCandidate]) -> list[PaperCandidate]:
    """Merge strong-identifier duplicates and mark weak duplicates without merging."""

    merged: list[PaperCandidate] = []
    strong_index: dict[str, int] = {}
    weak_seen: dict[str, int] = {}

    for paper in papers:
        strong_keys = []
        if paper.doi:
            value = normalize_doi(paper.doi)
            if value:
                strong_keys.append("doi:" + value)
        if paper.arxiv_id:
            value = normalize_arxiv(paper.arxiv_id)
            if value:
                strong_keys.append("arxiv:" + value)
        if paper.pmid:
            value = normalize_pmid(paper.pmid)
            if value:
                strong_keys.append("pmid:" + value)

        existing_index = next((strong_index[key] for key in strong_keys if key in strong_index), None)
        if existing_index is not None:
            merged[existing_index] = _merge_papers(merged[existing_index], paper)
            for key in strong_keys:
                strong_index[key] = existing_index
            continue

        weak_key = _weak_key(paper)
        if weak_key and weak_key in weak_seen:
            prior_index = weak_seen[weak_key]
            paper.suspected_duplicate = True
            paper.duplicate_reason = "标题、首作者和年份相同，但缺少可合并的强标识"
            merged[prior_index].suspected_duplicate = True
            merged[prior_index].duplicate_reason = paper.duplicate_reason
        elif weak_key:
            weak_seen[weak_key] = len(merged)

        merged.append(paper)
        new_index = len(merged) - 1
        for key in strong_keys:
            strong_index[key] = new_index

    for paper in merged:
        strong = _canonical_key(paper)
        paper.paper_id = "p_" + stable_hash(strong)
        if not paper.title:
            paper.title = "未命名文献"
    return merged


def rank_and_limit(papers: list[PaperCandidate], topic: str, limit: int) -> list[PaperCandidate]:
    topic_tokens = set(re.findall(r"[a-zA-Z]+|[\u3400-\u9fff]{1,2}", topic.lower()))

    def score(paper: PaperCandidate) -> tuple[float, int]:
        text = (paper.title + " " + paper.abstract).lower()
        overlap = sum(1 for token in topic_tokens if token and token in text)
        return (overlap, paper.year)

    return sorted(papers, key=score, reverse=True)[:limit]


def build_evidence(papers: list[PaperCandidate], max_chars: int) -> list[EvidenceFragment]:
    fragments: list[EvidenceFragment] = []
    for paper in papers:
        for index, sentence in enumerate(split_sentences(paper.abstract)[:8], start=1):
            quote = truncate(sentence, max_chars)
            if not quote:
                continue
            fragments.append(
                EvidenceFragment(
                    evidence_id="ev_" + stable_hash(paper.paper_id, str(index), quote, length=12),
                    paper_id=paper.paper_id,
                    quote=quote,
                    locator=f"摘要（Abstract），句子 {index}",
                    scope=EvidenceScope.ABSTRACT,
                )
            )
    return fragments


def _merge_papers(left: PaperCandidate, right: PaperCandidate) -> PaperCandidate:
    records = list(left.source_records)
    for record in right.source_records:
        if not any(
            item.source == record.source and item.source_id == record.source_id
            for item in records
        ):
            records.append(record)
    return PaperCandidate(
        paper_id=left.paper_id,
        title=max([left.title, right.title], key=len) if left.title else right.title,
        authors=left.authors or right.authors,
        year=min(left.year, right.year),
        abstract=max([left.abstract, right.abstract], key=len),
        doi=left.doi or right.doi,
        arxiv_id=left.arxiv_id or right.arxiv_id,
        pmid=left.pmid or right.pmid,
        url=left.url or right.url,
        peer_reviewed=left.peer_reviewed or right.peer_reviewed,
        evidence_scope=(
            EvidenceScope.FULLTEXT
            if EvidenceScope.FULLTEXT in (left.evidence_scope, right.evidence_scope)
            else EvidenceScope.ABSTRACT
        ),
        source_records=records,
        is_fixture=left.is_fixture or right.is_fixture,
        suspected_duplicate=left.suspected_duplicate or right.suspected_duplicate,
        duplicate_reason=left.duplicate_reason or right.duplicate_reason,
    )


def _canonical_key(paper: PaperCandidate) -> str:
    if paper.doi:
        return "doi:" + (normalize_doi(paper.doi) or "")
    if paper.arxiv_id:
        return "arxiv:" + (normalize_arxiv(paper.arxiv_id) or "")
    if paper.pmid:
        return "pmid:" + (normalize_pmid(paper.pmid) or "")
    return "weak:" + _weak_key(paper)


def _weak_key(paper: PaperCandidate) -> str:
    return "|".join(
        (
            normalize_title(paper.title),
            first_author_key(paper.authors),
            str(paper.year),
        )
    )


def _request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    **kwargs: object,
) -> httpx.Response:
    retries = 2
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = client.request(method, url, **kwargs)
            if response.status_code in {429, 500, 502, 503, 504}:
                retry_after = _retry_after_seconds(response)
                if attempt < retries:
                    time.sleep(min(retry_after, 10.0))
                    continue
                code = "rate_limited" if response.status_code == 429 else "service_unavailable"
                raise RetrievalError(code, f"HTTP {response.status_code}")
            if 400 <= response.status_code < 500:
                code = "permission_denied" if response.status_code in {401, 403} else "bad_request"
                raise RetrievalError(code, f"HTTP {response.status_code}")
            response.raise_for_status()
            return response
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise RetrievalError("network_error", str(exc)) from exc
    raise RetrievalError("network_error", str(last_error) if last_error else "unknown network error")


def _retry_after_seconds(response: httpx.Response) -> float:
    value = response.headers.get("Retry-After", "").strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        return 1.0


def _xml_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


def _extract_year(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(19|20)\d{2}", value)
    return int(match.group(0)) if match else None


def retriever(*, settings: Settings, search_agent: SearchAgent | None = None) -> LiteratureRetriever:
    return LiteratureRetriever(settings, search_agent=search_agent)
