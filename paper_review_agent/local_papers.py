from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .models import (
    EvidenceFragment,
    EvidenceScope,
    PaperCandidate,
    SourceName,
    SourceRecord,
    TaskCreateRequest,
)
from .retrieval import RetrievalResult, deduplicate_and_finalize
from .text import (
    normalize_arxiv,
    normalize_doi,
    normalize_space,
    split_sentences,
    stable_hash,
    truncate,
)


SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md"}
_SECTION_HINTS = (
    "abstract", "introduction", "method", "approach", "experiment", "evaluation",
    "result", "discussion", "limitation", "conclusion", "future work",
    "摘要", "引言", "方法", "实验", "结果", "局限", "结论", "未来工作",
)
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)
_ARXIV_RE = re.compile(r"(?:arXiv\s*:\s*)?(\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+/\d{7})(?:v\d+)?", re.I)
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


class LocalLibraryError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(slots=True)
class LocalDocument:
    path: Path
    source_id: str
    pages: list[str]
    metadata: dict[str, str]


class LocalPaperLibrary:
    def __init__(self, settings: Settings, root: Path | None = None) -> None:
        self.settings = settings
        self.root = root or settings.local_paper_dir

    def load(self, request: TaskCreateRequest) -> RetrievalResult:
        warnings: list[str] = []
        self.root.mkdir(parents=True, exist_ok=True)
        files = sorted(
            path for path in self.root.iterdir()
            if path.is_file()
            and path.suffix.lower() in SUPPORTED_SUFFIXES
            and not _is_readme_file(path)
        )
        if len(files) > self.settings.local_paper_max_files:
            warnings.append(
                f"本地论文文件数 {len(files)} 超过上限 {self.settings.local_paper_max_files}，"
                "仅处理按文件名排序后的前若干篇。"
            )
            files = files[: self.settings.local_paper_max_files]

        documents: list[LocalDocument] = []
        for path in files:
            try:
                document = self._read_document(path)
            except Exception as exc:
                warnings.append(f"本地论文读取失败，已跳过：{path.name}（{exc}）")
                continue
            text = "\n".join(document.pages)
            if len(normalize_space(text)) < 100:
                warnings.append(
                    f"本地论文未提取到足够文本，已跳过：{path.name}；扫描版 PDF 需要先做 OCR。"
                )
                continue
            documents.append(document)

        if not documents:
            raise LocalLibraryError(
                "empty_local_library",
                f"本地论文文件夹中没有可解析的 PDF/TXT/MD 论文：{self.root.resolve()}",
            )

        candidates = [self._candidate_from_document(document) for document in documents]
        papers = deduplicate_and_finalize(candidates)
        if len(papers) > request.candidate_limit:
            warnings.append(
                f"本地论文共识别 {len(papers)} 篇，候选上限为 {request.candidate_limit} 篇，"
                "仅展示前若干篇。"
            )
            papers = papers[: request.candidate_limit]

        documents_by_source = {document.source_id: document for document in documents}
        evidence: list[EvidenceFragment] = []
        for paper in papers:
            source_id = paper.source_records[0].source_id if paper.source_records else ""
            document = documents_by_source.get(source_id)
            if document is None:
                continue
            fragments = self._build_evidence(paper, document)
            evidence.extend(fragments)
            paper.evidence_count = len(fragments)
            paper.has_evidence = bool(fragments)

        if not evidence:
            raise LocalLibraryError(
                "local_evidence_empty",
                f"本地论文已读取，但未能建立可用全文证据：{self.root.resolve()}",
            )

        return RetrievalResult(
            papers=papers,
            evidence=evidence,
            warnings=warnings,
            source_mode="local",
            search_plan=None,
            screening_mode="local",
        )

    def _read_document(self, path: Path) -> LocalDocument:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            import pdfplumber

            with pdfplumber.open(path) as pdf:
                pages = [page.extract_text() or "" for page in pdf.pages]
                metadata = {
                    str(key).lstrip("/"): str(value)
                    for key, value in (pdf.metadata or {}).items()
                    if value is not None
                }
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
            pages = [part for part in text.split("\f")] or [text]
            metadata = {}
        return LocalDocument(
            path=path,
            source_id=path.name,
            pages=pages,
            metadata=metadata,
        )

    def _candidate_from_document(self, document: LocalDocument) -> PaperCandidate:
        text = "\n".join(document.pages)
        title, authors, year, doi, arxiv_id, abstract = _extract_metadata(
            text, document.metadata, document.path
        )
        file_hash = hashlib.sha256(document.path.read_bytes()).hexdigest()
        return PaperCandidate(
            paper_id="p_" + stable_hash(file_hash),
            title=title,
            authors=authors,
            year=year,
            abstract=abstract,
            doi=doi,
            arxiv_id=arxiv_id,
            url=None,
            peer_reviewed=False,
            evidence_scope=EvidenceScope.FULLTEXT,
            source_records=[
                SourceRecord(
                    source=SourceName.LOCAL,
                    source_id=document.source_id,
                    url=None,
                )
            ],
        )

    def _build_evidence(
        self, paper: PaperCandidate, document: LocalDocument
    ) -> list[EvidenceFragment]:
        chunk_limit = max(1, self.settings.local_paper_max_chunks_per_paper)
        target_chars = max(200, self.settings.local_evidence_chunk_chars)
        chunks: list[tuple[int, int, str]] = []
        for page_number, page_text in enumerate(document.pages, start=1):
            for chunk_index, chunk in enumerate(_chunk_page(page_text, target_chars), start=1):
                quote = truncate(chunk, target_chars)
                if quote:
                    chunks.append((page_number, chunk_index, quote))
        if not chunks:
            return []

        last_page = max(page for page, _, _ in chunks)
        ranked = sorted(
            enumerate(chunks),
            key=lambda item: (
                -_chunk_priority(item[1][0], last_page, item[1][2]),
                item[0],
            ),
        )
        selected_indexes = sorted(index for index, _ in ranked[:chunk_limit])
        suffix = "PDF" if document.path.suffix.lower() == ".pdf" else document.path.suffix.lstrip(".").upper()
        fragments: list[EvidenceFragment] = []
        for selected_index in selected_indexes:
            page_number, chunk_index, quote = chunks[selected_index]
            fragments.append(
                EvidenceFragment(
                    evidence_id="ev_" + stable_hash(
                        paper.paper_id, str(page_number), str(chunk_index), quote, length=12
                    ),
                    paper_id=paper.paper_id,
                    quote=quote,
                    locator=f"全文（{suffix}），第 {page_number} 页，片段 {chunk_index}",
                    scope=EvidenceScope.FULLTEXT,
                )
            )
        return fragments


def _extract_metadata(
    text: str,
    metadata: dict[str, str],
    path: Path,
) -> tuple[str, list[str], int, str | None, str | None, str]:
    normalized = normalize_space(text)
    first_page = text.split("\f", 1)[0]
    labeled_title = _labeled_value(text, "TITLE")
    metadata_title = normalize_space(metadata.get("Title", ""))
    title = (
        labeled_title
        or _extract_title_from_first_page(first_page)
        or (metadata_title if _plausible_title(metadata_title) else "")
        or path.stem.replace("_", " ").strip()
    )

    labeled_authors = _labeled_value(text, "AUTHORS") or _labeled_value(text, "AUTHOR")
    author_text = (
        labeled_authors
        or _extract_authors_from_first_page(first_page)
        or normalize_space(metadata.get("Author", ""))
    )
    authors = _split_authors(author_text)
    if not authors:
        authors = ["未识别作者"]

    arxiv_id = _arxiv_from_filename(path) or normalize_arxiv(_labeled_value(text, "ARXIV") or None)
    if arxiv_id is None:
        arxiv_match = _ARXIV_RE.search(first_page[:5000])
        arxiv_id = normalize_arxiv(arxiv_match.group(1)) if arxiv_match else None

    labeled_year = _labeled_value(text, "YEAR")
    year_match = _YEAR_RE.search(labeled_year) if labeled_year else None
    if year_match is None and arxiv_id:
        year = _year_from_arxiv_id(arxiv_id) or 2026
    else:
        year = int(year_match.group(0)) if year_match else 2026

    doi_match = _DOI_RE.search(first_page[:6000])
    doi = normalize_doi(doi_match.group(0).rstrip(".;,")) if doi_match else None
    abstract = _extract_abstract(text) or truncate(normalized, 1400)
    return title, authors, year, doi, arxiv_id, abstract


def _labeled_value(text: str, label: str) -> str:
    match = re.search(rf"(?im)^\s*{re.escape(label)}\s*:\s*(.+)$", text)
    return normalize_space(match.group(1)) if match else ""


def _is_readme_file(path: Path) -> bool:
    return path.stem.strip().lower().startswith(("readme", "license", "changelog"))


def _extract_title_from_first_page(text: str) -> str:
    title_lines: list[str] = []
    for raw_line in text.splitlines()[:24]:
        value = normalize_space(raw_line)
        lowered = value.lower()
        if not value or re.fullmatch(r"\d+", value):
            continue
        if lowered.startswith(("preprint", "arxiv", "http://", "https://")):
            continue
        if lowered.startswith(("abstract", "abstract—", "abstract–")):
            break
        if _looks_like_author_line(value):
            break
        if value.startswith(("AUTHORS:", "YEAR:", "DOI:", "ARXIV:")):
            continue
        if _plausible_title(value):
            title_lines.append(value)
        if len(title_lines) >= 4:
            break
    return " ".join(title_lines)


def _extract_authors_from_first_page(text: str) -> str:
    author_lines: list[str] = []
    for raw_line in text.splitlines()[:24]:
        value = normalize_space(raw_line)
        if not value:
            if author_lines:
                break
            continue
        if _looks_like_affiliation_line(value):
            if author_lines:
                break
            continue
        if not author_lines:
            if _looks_like_author_line(value):
                author_lines.append(value)
            continue
        previous = author_lines[-1]
        if (
            _looks_like_author_line(value)
            or value.count(",") >= 1
            or " and " in value.lower()
            or previous.endswith(",")
        ):
            author_lines.append(value)
            continue
        break
    return " ".join(author_lines)


def _looks_like_author_line(value: str) -> bool:
    if not value or len(value) > 500:
        return False
    if "@" in value or "(cid:" in value:
        return True
    if any(marker in value for marker in ("†", "‡", "§", "*")) and "," in value:
        return True
    return value.count(",") >= 3


def _looks_like_affiliation_line(value: str) -> bool:
    lowered = value.lower()
    return any(
        marker in lowered
        for marker in (
            "university", "institute", "laboratory", "department", "college",
            "research center", "research centre", "school of", "academy",
        )
    )


def _plausible_title(value: str) -> bool:
    lowered = value.lower().strip()
    if lowered in {"preprint", "preprint.", "untitled", "microsoft word - document"}:
        return False
    return 5 <= len(value) <= 240 and not lowered.startswith(("arxiv", "http://", "https://"))


def _arxiv_from_filename(path: Path) -> str | None:
    match = re.search(r"(?<!\d)(\d{4}\.\d{4,5})(?:v\d+)?", path.stem)
    return normalize_arxiv(match.group(1)) if match else None


def _year_from_arxiv_id(arxiv_id: str) -> int | None:
    match = re.match(r"(\d{2})(\d{2})\.", arxiv_id)
    if not match:
        return None
    year = int(match.group(1))
    return 1900 + year if year >= 91 else 2000 + year


def _split_authors(value: str) -> list[str]:
    if not value:
        return []
    cleaned = re.sub(r"\(cid:\d+\)", "", value)
    cleaned = re.sub(r"[†‡§*]", "", cleaned)
    cleaned = re.sub(r"(?<=[A-Za-z])\d+", "", cleaned)
    pieces = re.split(r";|,|\s+and\s+", cleaned)
    authors = [normalize_space(piece) for piece in pieces if normalize_space(piece)]
    authors = [author for author in authors if 2 <= len(author) <= 120]
    return authors[:20]


def _extract_abstract(text: str) -> str:
    match = re.search(
        r"(?is)\babstract\b\s*(?:—|–|-|:|\.)?\s*(.*?)(?=\n\s*(?:\d+\.?\s*)?(?:introduction|keywords)\b|\n\s*1\s+introduction\b)",
        text,
    )
    if match:
        return truncate(normalize_space(match.group(1)), 1400)
    return ""


def _chunk_page(text: str, target_chars: int) -> list[str]:
    cleaned = text.replace("\r", "\n")
    paragraphs = [normalize_space(part) for part in re.split(r"\n\s*\n", cleaned) if normalize_space(part)]
    if len(paragraphs) <= 1:
        paragraphs = [normalize_space(cleaned)]
    chunks: list[str] = []
    for paragraph in paragraphs:
        if not paragraph:
            continue
        if len(paragraph) <= target_chars:
            chunks.append(paragraph)
            continue
        current = ""
        for sentence in split_sentences(paragraph):
            piece = normalize_space(sentence)
            if not piece:
                continue
            if current and len(current) + len(piece) + 1 > target_chars:
                chunks.append(current)
                current = piece
            else:
                current = f"{current} {piece}".strip()
        if current:
            chunks.append(current)
    return chunks


def _chunk_priority(page_number: int, last_page: int, quote: str) -> int:
    score = 3 if page_number <= 2 else 0
    lowered = quote.lower()
    score += sum(2 for hint in _SECTION_HINTS if hint in lowered)
    score += 2 if page_number >= max(1, last_page - 1) else 0
    return score
