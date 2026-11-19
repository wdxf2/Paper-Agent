from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from paper_review_agent.models import (
    EVALUATION_DIMENSIONS,
    EVALUATION_SCALE_VERSION,
    EvaluationRequest,
    SourceName,
    TaskCreateRequest,
)


def test_topic_trim_and_boundaries():
    request = TaskCreateRequest(topic="  " + "研" * 200 + "  ")
    assert request.topic == "研" * 200
    with pytest.raises(ValidationError):
        TaskCreateRequest(topic="研" * 201)
    with pytest.raises(ValidationError):
        TaskCreateRequest(topic="   ")


def test_year_and_limit_rules():
    current = date.today().year
    with pytest.raises(ValidationError):
        TaskCreateRequest(topic="topic", year_start=2025, year_end=2020)
    with pytest.raises(ValidationError):
        TaskCreateRequest(topic="topic", year_end=current + 1)
    with pytest.raises(ValidationError):
        TaskCreateRequest(topic="topic", candidate_limit=0)
    with pytest.raises(ValidationError):
        TaskCreateRequest(topic="topic", candidate_limit=51)
    assert TaskCreateRequest(topic="topic", candidate_limit=1).candidate_limit == 1
    assert TaskCreateRequest(topic="topic", candidate_limit=50).candidate_limit == 50


def test_sources_are_unique_and_nonempty():
    request = TaskCreateRequest(
        topic="topic", sources=[SourceName.ARXIV, SourceName.ARXIV, SourceName.PUBMED]
    )
    assert request.sources == [SourceName.ARXIV, SourceName.PUBMED]
    with pytest.raises(ValidationError):
        TaskCreateRequest(topic="topic", sources=[])


def test_evaluation_scale_shape():
    scores = {key: 4 for key in EVALUATION_DIMENSIONS}
    request = EvaluationRequest(
        reviewer_id="reviewer-01",
        scale_version=EVALUATION_SCALE_VERSION,
        scores=scores,
        comments="controlled test",
    )
    assert request.scores == scores
    with pytest.raises(ValidationError):
        EvaluationRequest(
            reviewer_id="reviewer-01",
            scale_version=EVALUATION_SCALE_VERSION,
            scores={EVALUATION_DIMENSIONS[0]: 4},
        )
    with pytest.raises(ValidationError):
        EvaluationRequest(
            reviewer_id="reviewer-01",
            scale_version=EVALUATION_SCALE_VERSION,
            scores={**scores, EVALUATION_DIMENSIONS[0]: 6},
        )
