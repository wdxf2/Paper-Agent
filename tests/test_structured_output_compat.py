from __future__ import annotations

import json

from crewai import Crew

from paper_review_agent.config import Settings
from paper_review_agent.crew import CrewAIReviewRunner
from paper_review_agent.models import PaperCandidate, SearchPlan, SourceName, SourceRecord, TaskCreateRequest
from paper_review_agent.models import PaperEvidenceBundle, EvidenceFragment, EvidencePack


class FakeTaskOutput:
    def __init__(self, payload: dict | str) -> None:
        self.raw = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)


class FakeCrewResult:
    def __init__(self, *payloads: dict | str) -> None:
        self.tasks_output = [FakeTaskOutput(payload) for payload in payloads]


def test_plan_search_uses_json_text_for_compatible_endpoint(monkeypatch, tmp_path):
    captured = {}

    def fake_kickoff(self):
        captured["tasks"] = self.tasks
        return FakeCrewResult(
            {
                "topic": "大模型辅助科研文献综述",
                "keywords": ["large language model", "literature review"],
                "queries": ["large language model literature review"],
                "rationale": "使用英文检索式。",
                "mode": "llm",
            }
        )

    monkeypatch.setattr(Crew, "kickoff", fake_kickoff)
    runner = CrewAIReviewRunner(
        Settings(
            database_path=tmp_path / "compat.db",
            llm_model="deepseek-flash",
            llm_api_key="test-key",
            llm_base_url="https://api.deepseek.com",
        )
    )

    plan = runner.plan_search(
        TaskCreateRequest(
            topic="大模型辅助科研文献综述",
            keywords=["引用核验"],
            sources=[SourceName.ARXIV],
            candidate_limit=5,
        )
    )

    assert captured["tasks"][0].output_pydantic is None
    assert "JSON" in captured["tasks"][0].description
    assert plan.queries == ["large language model literature review"]


def test_plan_search_cleans_real_model_json_noise(monkeypatch, tmp_path):
    long_english = (
        '("large language model" OR "large language models" OR LLM OR LLMs OR GPT) '
        'AND ("literature review" OR "systematic review" OR "literature survey" OR '
        '"related work" OR "review generation") AND (generation OR automation OR '
        '"review writing" OR "evidence synthesis") AND (2018-2026)'
    )
    wrapped = {
        "topic": "大模型辅助科研文献综述",
        "keywords": ["citation verification"],
        "queries": [
            long_english,
            '("citation verification" OR "reference checking") AND (2018-2026)',
            '("大语言模型" OR LLM) AND ("文献综述" OR "引用核验")',
        ],
        "rationale": "只保留英文检索式，年份由数据源过滤。",
        "mode": "llm",
    }
    raw = "下面是结果：\n```json\n" + json.dumps(wrapped, ensure_ascii=False) + "\n```"

    def fake_kickoff(self):
        return FakeCrewResult(raw)

    monkeypatch.setattr(Crew, "kickoff", fake_kickoff)
    runner = CrewAIReviewRunner(
        Settings(
            database_path=tmp_path / "compat.db",
            llm_model="deepseek-flash",
            llm_api_key="test-key",
            llm_base_url="https://api.deepseek.com",
        )
    )

    plan = runner.plan_search(
        TaskCreateRequest(
            topic="大模型辅助科研文献综述",
            keywords=["引用核验"],
            year_start=2018,
            year_end=2026,
            sources=[SourceName.ARXIV],
            candidate_limit=5,
        )
    )

    assert len(plan.queries) == 2
    assert all("2018-2026" not in query for query in plan.queries)
    assert all(not any("\u3400" <= char <= "\u9fff" for char in query) for query in plan.queries)


def test_screening_uses_json_text_for_compatible_endpoint(monkeypatch, tmp_path):
    captured = {}
    candidate = PaperCandidate(
        paper_id="p1",
        title="Large language models for literature review",
        authors=["A"],
        year=2025,
        abstract="A retrieval augmented method for scientific literature review.",
        source_records=[SourceRecord(source=SourceName.ARXIV, source_id="1")],
    )
    request = TaskCreateRequest(
        topic="大模型辅助科研文献综述",
        keywords=["literature review"],
        sources=[SourceName.ARXIV],
        candidate_limit=5,
    )
    plan = SearchPlan(
        topic=request.topic,
        keywords=request.keywords,
        queries=["large language model literature review"],
        mode="llm",
    )

    def fake_kickoff(self):
        captured["tasks"] = self.tasks
        return FakeCrewResult(
            {
                "selections": [
                    {
                        "paper_id": "p1",
                        "relevance_score": 92,
                        "decision": "include",
                        "reason": "主题与摘要匹配。",
                        "matched_keywords": ["literature review"],
                    }
                ],
                "overall_reason": "保留明确相关文献。",
            }
        )

    monkeypatch.setattr(Crew, "kickoff", fake_kickoff)
    runner = CrewAIReviewRunner(
        Settings(
            database_path=tmp_path / "compat.db",
            llm_model="deepseek-flash",
            llm_api_key="test-key",
            llm_base_url="https://api.deepseek.com",
        )
    )

    result = runner.screen_candidates(request, plan, [candidate])

    assert captured["tasks"][0].output_pydantic is None
    assert "JSON" in captured["tasks"][0].description
    assert result.selections[0].paper_id == "p1"


def test_review_tasks_use_json_text_for_compatible_endpoint(monkeypatch, tmp_path):
    captured = {}
    paper = PaperCandidate(
        paper_id="p1",
        title="Large language models for literature review",
        authors=["A"],
        year=2025,
        abstract="A retrieval augmented method checks citation evidence.",
        source_records=[SourceRecord(source=SourceName.ARXIV, source_id="1")],
    )
    fragment = EvidenceFragment(
        evidence_id="e1",
        paper_id="p1",
        quote="A retrieval augmented method checks citation evidence.",
        locator="Abstract, sentence 1",
    )
    pack = EvidencePack(
        topic="大模型辅助科研文献综述",
        year_start=2020,
        year_end=2026,
        papers=[PaperEvidenceBundle(paper=paper, evidence_ids=["e1"])],
        evidence=[fragment],
    )

    def fake_kickoff(self):
        captured["tasks"] = self.tasks
        return FakeCrewResult(
            pack.model_dump(mode="json"),
            {
                "papers": [
                    {
                        "paper_id": "p1",
                        "title": paper.title,
                        "methods": ["retrieval augmented review"],
                        "experimental_design": "未报告或无法判断",
                        "innovations": ["citation evidence"],
                        "limitations": ["需要全文核验"],
                        "evidence_ids": ["e1"],
                    }
                ],
                "coverage_notes": [],
            },
            {
                "categories": ["检索增强生成"],
                "similarities": [],
                "differences": [],
                "evolution": [],
                "open_questions": [],
                "caveats": [],
            },
            {
                "title": "测试综述",
                "claims": [
                    {
                        "claim_id": "c1",
                        "section": "background",
                        "text": "测试背景。",
                        "evidence_ids": ["e1"],
                        "subject_paper_ids": ["p1"],
                        "kind": "evidence",
                    },
                    {
                        "claim_id": "c2",
                        "section": "methods",
                        "text": "测试方法。",
                        "evidence_ids": ["e1"],
                        "subject_paper_ids": ["p1"],
                        "kind": "evidence",
                    },
                    {
                        "claim_id": "c3",
                        "section": "evolution",
                        "text": "测试演进。",
                        "evidence_ids": ["e1"],
                        "subject_paper_ids": ["p1"],
                        "kind": "evidence",
                    },
                    {
                        "claim_id": "c4",
                        "section": "open_questions",
                        "text": "测试问题。",
                        "evidence_ids": ["e1"],
                        "subject_paper_ids": ["p1"],
                        "kind": "evidence",
                    },
                ],
                "coverage_notes": [],
            },
        )

    monkeypatch.setattr(Crew, "kickoff", fake_kickoff)
    runner = CrewAIReviewRunner(
        Settings(
            database_path=tmp_path / "compat.db",
            llm_model="deepseek-flash",
            llm_api_key="test-key",
            llm_base_url="https://api.deepseek.com",
            rag_top_k=4,
        )
    )

    result = runner.run("task-compat", pack)

    assert len(captured["tasks"]) == 4
    assert all(task.output_pydantic is None for task in captured["tasks"])
    assert all("JSON" in task.description for task in captured["tasks"])
    assert result.draft.title == "测试综述"
