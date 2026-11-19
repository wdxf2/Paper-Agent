from __future__ import annotations

import pytest
from pydantic import ValidationError

from paper_review_agent.models import CandidateScreening, SearchPlan, TaskCreateRequest


def test_keywords_accept_comma_separated_chinese_and_deduplicate():
    request = TaskCreateRequest(topic="综述", keywords=" RAG，引用核验, RAG , 多智能体 ")
    assert request.keywords == ["RAG", "引用核验", "多智能体"]


def test_blank_keywords_are_removed_and_overlong_keywords_are_rejected():
    assert TaskCreateRequest(topic="topic", keywords=["   ", "RAG"]).keywords == ["RAG"]
    with pytest.raises(ValidationError):
        TaskCreateRequest(topic="topic", keywords=["x" * 81])


def test_search_plan_rejects_empty_queries():
    with pytest.raises(ValidationError):
        SearchPlan(topic="topic", queries=["   "])


def test_screening_score_boundaries():
    assert CandidateScreening(paper_id="p", relevance_score=0).relevance_score == 0
    assert CandidateScreening(paper_id="p", relevance_score=100).relevance_score == 100
    with pytest.raises(ValidationError):
        CandidateScreening(paper_id="p", relevance_score=-1)
    with pytest.raises(ValidationError):
        CandidateScreening(paper_id="p", relevance_score=101)
