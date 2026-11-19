from __future__ import annotations

from typing import Protocol

from paper_review_agent.models import CandidateScreening, PaperCandidate, ScreeningResult
from paper_review_agent.text import normalize_space


class ScreeningPolicy(Protocol):
    def screen(self, topic: str, keywords: list[str], candidates: list[PaperCandidate]) -> ScreeningResult: ...


class HeuristicScreener:
    def screen(self, topic: str, keywords: list[str], candidates: list[PaperCandidate]) -> ScreeningResult:
        terms = [item for item in ([topic, *keywords]) if item.strip()]
        selections: list[CandidateScreening] = []
        for candidate in candidates:
            text = (candidate.title + "\n" + candidate.abstract).lower()
            matched = [term for term in terms if normalize_space(term).lower() in text]
            if matched:
                score = min(95, 55 + len(matched) * 20)
                decision = "include"
            else:
                # The no-key demo path keeps a controlled candidate pool visible and
                # labels low-confidence items instead of pretending they are excluded.
                score = 35
                decision = "borderline"
            selections.append(
                CandidateScreening(
                    paper_id=candidate.paper_id,
                    relevance_score=score,
                    decision=decision,
                    reason="按关键词与标题/摘要的词面重合度回退筛选。",
                    matched_keywords=matched,
                )
            )
        return ScreeningResult(selections=selections, overall_reason="未调用大模型，使用词面规则回退。")
