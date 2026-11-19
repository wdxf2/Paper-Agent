from __future__ import annotations

from paper_review_agent.retrieval import build_arxiv_query, build_pubmed_query


def test_arxiv_query_adds_default_field_to_boolean_terms():
    query = build_arxiv_query(
        ['"large language model" AND ("literature review" OR survey)']
    )
    assert query == '(all:"large language model" AND (all:"literature review" OR all:survey))'


def test_arxiv_query_preserves_supported_field_prefixes():
    query = build_arxiv_query(['all:"RAG" AND ti:review'])
    assert query == '(all:"RAG" AND ti:review)'


def test_pubmed_query_removes_arxiv_fields_and_keeps_boolean_groups():
    query = build_pubmed_query(
        ['all:"large language model" AND (all:"literature review" OR all:survey)']
    )
    assert query == '("large language model" AND ("literature review" OR survey))'


def test_plain_phrase_is_quoted_as_one_arxiv_phrase():
    query = build_arxiv_query(['large language model literature review'])
    assert query == 'all:"large language model literature review"'
