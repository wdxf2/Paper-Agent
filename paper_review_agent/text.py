from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable


_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_\-]*|\d+(?:\.\d+)?")
_SENTENCE_RE = re.compile(r"(?<=[。！？!?；;.])\s*")


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", value)


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    value = normalize_space(value).lower()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    return value.strip(" .;,") or None


def normalize_arxiv(value: str | None) -> str | None:
    if not value:
        return None
    value = normalize_space(value).lower()
    value = re.sub(r"^arxiv:\s*", "", value)
    value = re.sub(r"^https?://arxiv\.org/(?:abs|pdf)/", "", value)
    value = re.sub(r"\.pdf$", "", value)
    value = re.sub(r"v\d+$", "", value)
    return value.strip("/ ") or None


def normalize_pmid(value: str | None) -> str | None:
    if not value:
        return None
    value = normalize_space(value).lower()
    value = re.sub(r"^pmid:\s*", "", value)
    return value.strip() or None


def stable_hash(*parts: str | None, length: int = 16) -> str:
    raw = "\x1f".join((part or "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def split_sentences(text: str) -> list[str]:
    text = normalize_space(text)
    if not text:
        return []
    pieces = [piece.strip() for piece in _SENTENCE_RE.split(text) if piece.strip()]
    if len(pieces) <= 1:
        pieces = [piece.strip() for piece in re.split(r"(?<=[,，])\s+", text) if piece.strip()]
    return pieces or [text]


def truncate(text: str, limit: int) -> str:
    text = normalize_space(text)
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text or "").lower()
    tokens = [match.group(0) for match in _WORD_RE.finditer(text)]
    cjk_runs = re.findall(r"[\u3400-\u9fff]+", text)
    for run in cjk_runs:
        tokens.extend(run)
        tokens.extend(run[index : index + 2] for index in range(max(0, len(run) - 1)))
    return tokens


def lexical_support(claim: str, evidence_quotes: Iterable[str]) -> float:
    claim_tokens = set(tokenize(claim))
    if not claim_tokens:
        return 0.0
    evidence_tokens = set(tokenize(" ".join(evidence_quotes)))
    if not evidence_tokens:
        return 0.0
    overlap = claim_tokens & evidence_tokens
    return len(overlap) / max(1, len(claim_tokens))


def json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def json_loads(value: str | None, default: object) -> object:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def first_author_key(authors: list[str]) -> str:
    if not authors:
        return ""
    first = normalize_space(authors[0]).lower()
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", first)
