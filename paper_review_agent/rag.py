from __future__ import annotations

import math
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass

from .models import EvidenceFragment, EvidencePack
from .text import tokenize


@dataclass(slots=True)
class RagHit:
    fragment: EvidenceFragment
    score: float


class EvidenceIndex:
    """Small in-memory hybrid retriever: BM25 + hashed character-vector cosine."""

    def __init__(self, fragments: list[EvidenceFragment]) -> None:
        self.fragments = fragments
        self._tokens = [tokenize(fragment.quote) for fragment in fragments]
        self._term_freq = [Counter(tokens) for tokens in self._tokens]
        self._doc_len = [max(1, len(tokens)) for tokens in self._tokens]
        self._avg_len = sum(self._doc_len) / max(1, len(self._doc_len))
        self._df: Counter[str] = Counter()
        for tokens in self._tokens:
            self._df.update(set(tokens))
        self._vectors = [self._vectorize(fragment.quote) for fragment in fragments]

    def search(self, query: str, top_k: int = 8, max_per_paper: int = 2) -> list[RagHit]:
        if not self.fragments:
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            query_tokens = ["review"]
        query_vector = self._vectorize(query)
        raw: list[tuple[int, float]] = []
        for index, fragment in enumerate(self.fragments):
            bm25 = self._bm25(query_tokens, index)
            cosine = self._cosine(query_vector, self._vectors[index])
            score = 0.65 * bm25 + 0.35 * cosine
            raw.append((index, score))
        raw.sort(key=lambda item: item[1], reverse=True)

        hits: list[RagHit] = []
        per_paper: Counter[str] = Counter()
        for index, score in raw:
            fragment = self.fragments[index]
            if per_paper[fragment.paper_id] >= max_per_paper:
                continue
            hits.append(RagHit(fragment=fragment, score=score))
            per_paper[fragment.paper_id] += 1
            if len(hits) >= top_k:
                break
        return hits

    def _bm25(self, query_tokens: list[str], index: int, k1: float = 1.5, b: float = 0.75) -> float:
        total_docs = max(1, len(self.fragments))
        score = 0.0
        freqs = self._term_freq[index]
        doc_len = self._doc_len[index]
        for term in query_tokens:
            freq = freqs.get(term, 0)
            if not freq:
                continue
            doc_freq = self._df.get(term, 0)
            idf = math.log(1 + (total_docs - doc_freq + 0.5) / (doc_freq + 0.5))
            denominator = freq + k1 * (1 - b + b * doc_len / max(1e-9, self._avg_len))
            score += idf * (freq * (k1 + 1)) / denominator
        return score / max(1.0, math.log(1 + len(query_tokens)))

    @staticmethod
    def _vectorize(text: str, dimensions: int = 512) -> dict[int, float]:
        tokens = tokenize(text)
        if not tokens:
            return {}
        features = list(tokens)
        features.extend(" ".join(tokens[index : index + 2]) for index in range(len(tokens) - 1))
        vector: Counter[int] = Counter()
        for feature in features:
            bucket = zlib.crc32(feature.encode("utf-8")) % dimensions
            vector[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vector.values())) or 1.0
        return {bucket: value / norm for bucket, value in vector.items()}

    @staticmethod
    def _cosine(left: dict[int, float], right: dict[int, float]) -> float:
        if len(left) > len(right):
            left, right = right, left
        return sum(value * right.get(bucket, 0.0) for bucket, value in left.items())


def build_writer_rag_context(pack: EvidencePack, top_k: int = 12) -> list[EvidenceFragment]:
    index = EvidenceIndex(pack.evidence)
    queries = [
        pack.topic + " 研究背景 问题 现状",
        pack.topic + " 方法 框架 模型 分类",
        pack.topic + " 技术演进 时间 发展",
        pack.topic + " 局限 未解决问题 未来工作",
    ]
    selected: dict[str, EvidenceFragment] = {}
    for query in queries:
        for hit in index.search(query, top_k=max(3, top_k // 2), max_per_paper=1):
            selected.setdefault(hit.fragment.evidence_id, hit.fragment)
    if len(selected) < min(top_k, len(pack.evidence)):
        for hit in index.search(pack.topic, top_k=top_k, max_per_paper=1):
            selected.setdefault(hit.fragment.evidence_id, hit.fragment)
    return list(selected.values())[:top_k]
