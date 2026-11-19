from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from PAPER_AGENT_* environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="PAPER_AGENT_",
        extra="ignore",
    )

    app_name: str = "科研文献智能综述生成系统"
    host: str = "127.0.0.1"
    port: int = 8000
    database_path: Path = Path("data/paper_review.db")
    engine_mode: Literal["crewai", "local"] = "crewai"
    llm_model: str = "openai/gpt-4o-mini"
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_temperature: float = 0.1
    # native: provider JSON schema; json_text: prompt-only JSON for OpenAI-compatible APIs
    llm_structured_output_mode: Literal["auto", "native", "json_text"] = "auto"
    offline_fallback: bool = True
    request_timeout_seconds: float = 30.0
    retrieval_retries: int = 2
    search_pool_multiplier: int = 4
    search_pool_min: int = 20
    search_pool_max: int = 40
    screening_abstract_chars: int = 900
    background_workers: int = 2
    max_evidence_chars: int = 1200
    local_paper_dir: Path = Path("local_papers/inbox")
    local_paper_max_files: int = 50
    local_paper_max_chunks_per_paper: int = 10
    local_evidence_chunk_chars: int = 900
    rag_top_k: int = 12
    default_sources: list[str] = Field(default_factory=lambda: ["arxiv", "pubmed"])
    user_agent: str = "PaperReviewAgent/0.1 (research prototype)"
    pubmed_tool: str = "paper_review_agent"
    pubmed_email: str | None = None
    session_cookie: str = "paper_agent_session"
    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings()
