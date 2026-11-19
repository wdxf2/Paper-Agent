from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import crewai

from .config import Settings
from .crew import CrewAIReviewRunner, LocalReviewRunner, ReviewRunResult
from .models import (
    AgentRole,
    AgentStatus,
    AnalysisView,
    CandidateListView,
    ConfirmSelectionRequest,
    EvaluationRequest,
    EvaluationView,
    EvidencePack,
    HealthView,
    ReportView,
    SourceName,
    TaskCreateRequest,
    TaskStatus,
    TaskView,
)
from .local_papers import LocalLibraryError, LocalPaperLibrary
from .repository import InvalidTransition, Repository
from .retrieval import LiteratureRetriever, RetrievalError, RetrievalResult
from .text import json_loads
from .validation import CitationValidator, ReportValidationError, prepare_report


logger = logging.getLogger(__name__)


class ReviewService:
    def __init__(
        self,
        settings: Settings,
        *,
        repository: Repository | None = None,
        retriever: LiteratureRetriever | None = None,
        local_library: LocalPaperLibrary | None = None,
        runner: CrewAIReviewRunner | LocalReviewRunner | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository or Repository(settings.database_path)
        if runner is not None:
            self.runner = runner
        elif settings.engine_mode == "local":
            self.runner = LocalReviewRunner()
        else:
            self.runner = CrewAIReviewRunner(settings)
        self.retriever = retriever or LiteratureRetriever(
            settings,
            search_agent=self.runner if settings.engine_mode != "local" else None,
        )
        self.local_library = local_library or LocalPaperLibrary(settings)
        self.executor = ThreadPoolExecutor(
            max_workers=max(1, settings.background_workers),
            thread_name_prefix="paper-review",
        )
        self._bootstrapped = False

    def bootstrap(self) -> None:
        if self._bootstrapped:
            return
        self.repository.init_db()
        interrupted = self.repository.mark_stale_tasks()
        if interrupted:
            logger.warning("Marked %s interrupted task(s) as failed", interrupted)
        self._bootstrapped = True

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)

    @property
    def llm_mode(self) -> str:
        return getattr(self.runner, "llm_mode", "unknown")

    def create_task(self, request: TaskCreateRequest, owner_session: str) -> TaskView:
        task = self.repository.create_task(request, owner_session)
        local_mode = SourceName.LOCAL in request.sources
        self.repository.transition(
            task.task_id,
            TaskStatus.RETRIEVING,
            "local_ingestion" if local_mode else "retrieval",
            (
                "正在读取本地论文文件夹并建立全文证据"
                if local_mode
                else "正在规划检索式、检索候选并调用模型筛选文献"
            ),
            10,
        )
        self.repository.start_agent(
            task.task_id,
            AgentRole.RETRIEVAL,
            "local_paper_library" if local_mode else "academic_search",
        )
        self.executor.submit(self._run_retrieval, task.task_id, owner_session)
        return self.repository.get_task(task.task_id, owner_session)

    def retry_task(self, original_task_id: str, owner_session: str) -> TaskView:
        original = self.repository.get_task(original_task_id, owner_session)
        if original.status != TaskStatus.FAILED:
            raise InvalidTransition("只有已失败任务可以创建重试任务")
        task = self.repository.create_retry_task(original_task_id, owner_session)
        local_mode = SourceName.LOCAL in original.sources
        self.repository.transition(
            task.task_id,
            TaskStatus.RETRIEVING,
            "retry_local_ingestion" if local_mode else "retry_retrieval",
            (
                f"重试原任务 {original_task_id}，正在重新读取本地论文文件夹"
                if local_mode
                else f"重试原任务 {original_task_id}，正在重新规划检索式并筛选候选文献"
            ),
            10,
        )
        self.repository.start_agent(
            task.task_id,
            AgentRole.RETRIEVAL,
            "local_paper_library_retry" if local_mode else "academic_search_retry",
        )
        self.executor.submit(self._run_retrieval, task.task_id, owner_session)
        return self.repository.get_task(task.task_id, owner_session)

    def confirm_selection(
        self, task_id: str, request: ConfirmSelectionRequest, owner_session: str
    ) -> TaskView:
        selected = self.repository.confirm_selection(task_id, request.paper_ids, owner_session)
        self.repository.transition(
            task_id, TaskStatus.ANALYZING, "confirmed",
            "文献选择快照已固定，开始单篇分析与跨文献融合", 20,
        )
        self.repository.start_agent(task_id, AgentRole.RETRIEVAL, ",".join(selected))
        self.executor.submit(self._run_generation, task_id, owner_session)
        return self.repository.get_task(task_id, owner_session)

    def list_tasks(self, owner_session: str) -> list[TaskView]:
        return self.repository.list_tasks(owner_session)

    def get_task(self, task_id: str, owner_session: str) -> TaskView:
        return self.repository.get_task(task_id, owner_session)

    def get_candidates(self, task_id: str, owner_session: str) -> CandidateListView:
        return self.repository.list_candidates(task_id, owner_session)

    def get_analysis(self, task_id: str, owner_session: str) -> AnalysisView:
        analysis, comparison = self.repository.get_analysis_view(task_id, owner_session)
        return AnalysisView(task_id=task_id, analysis=analysis, comparison=comparison)

    def get_report(self, task_id: str, owner_session: str) -> ReportView:
        return self.repository.get_report_for_task(task_id, owner_session)

    def get_report_by_id(self, report_id: str, owner_session: str) -> ReportView:
        return self.repository.get_report(report_id, owner_session)

    def create_evaluation(
        self, report_id: str, request: EvaluationRequest, owner_session: str
    ) -> EvaluationView:
        return self.repository.create_evaluation(report_id, request, owner_session)

    def list_evaluations(self, report_id: str, owner_session: str) -> list[EvaluationView]:
        return self.repository.list_evaluations(report_id, owner_session)

    def health(self) -> HealthView:
        ready = False
        try:
            with self.repository.connect() as connection:
                connection.execute("SELECT 1").fetchone()
            ready = True
        except Exception:
            ready = False
        return HealthView(
            status="ok" if ready else "degraded",
            app=self.settings.app_name,
            crewai_version=getattr(crewai, "__version__", "unknown"),
            engine_mode=self.settings.engine_mode,
            llm_mode=self.llm_mode,
            database_ready=ready,
        )

    def _run_retrieval(self, task_id: str, owner_session: str) -> None:
        try:
            row = self.repository.get_task_raw(task_id, owner_session)
            request = TaskCreateRequest(
                topic=row["topic"],
                year_start=int(row["year_start"]),
                year_end=int(row["year_end"]),
                keywords=json_loads(row["keywords_json"], []),
                sources=[SourceName(item) for item in json_loads(row["sources_json"], [])],
                candidate_limit=int(row["candidate_limit"]),
            )
            if SourceName.LOCAL in request.sources:
                result: RetrievalResult = self.local_library.load(request)
            else:
                result = self.retriever.retrieve(request)
            self.repository.save_candidates(
                task_id, result.papers, result.evidence, result.warnings, result.source_mode
            )
            if result.search_plan is not None:
                self.repository.save_artifact(task_id, "search_plan", result.search_plan)
            self.repository.save_artifact(
                task_id,
                "search_meta",
                {
                    "screening_mode": result.screening_mode,
                    "planning_mode": (
                        result.search_plan.mode
                        if result.search_plan
                        else ("local" if result.source_mode == "local" else "heuristic")
                    ),
                    "local_paper_dir": str(self.settings.local_paper_dir.resolve()),
                },
            )
            self.repository.finish_agent(
                task_id, AgentRole.RETRIEVAL, AgentStatus.SUCCEEDED,
                output_ref="candidate_snapshot",
                payload={
                    "paper_count": len(result.papers),
                    "evidence_count": len(result.evidence),
                    "screening_mode": result.screening_mode,
                },
            )
            available = sum(1 for paper in result.papers if paper.has_evidence)
            local_result = result.source_mode == "local"
            completion_label = "本地论文读取完成" if local_result else "检索完成"
            evidence_label = "全文证据" if local_result else "可用证据"
            self.repository.transition(
                task_id,
                TaskStatus.AWAITING_CONFIRMATION,
                "candidates_ready",
                f"{completion_label}：{len(result.papers)} 篇候选，{available} 篇具备{evidence_label}，等待用户确认",
                30,
            )
        except LocalLibraryError as exc:
            self.repository.finish_agent(
                task_id, AgentRole.RETRIEVAL, AgentStatus.FAILED, error=f"{exc.code}: {exc.message}"
            )
            self.repository.fail_task(
                task_id, "retrieval", f"本地论文读取失败（{exc.code}）：{exc.message}"
            )
        except RetrievalError as exc:
            self.repository.finish_agent(
                task_id, AgentRole.RETRIEVAL, AgentStatus.FAILED, error=f"{exc.code}: {exc.message}"
            )
            self.repository.fail_task(task_id, "retrieval", f"检索失败（{exc.code}）：{exc.message}")
        except Exception as exc:
            logger.exception("Unexpected retrieval failure for %s", task_id)
            self.repository.finish_agent(
                task_id, AgentRole.RETRIEVAL, AgentStatus.FAILED, error=str(exc)
            )
            self.repository.fail_task(task_id, "retrieval", f"检索阶段发生异常：{exc}")

    def _run_generation(self, task_id: str, owner_session: str) -> None:
        started_roles: set[AgentRole] = set()
        finished_roles: set[AgentRole] = set()
        current_stage = {"name": "evidence_preparation"}

        def on_start(role: AgentRole) -> None:
            started_roles.add(role)
            selected = self.repository.get_task_raw(task_id, owner_session)["selected_paper_ids_json"]
            self.repository.start_agent(task_id, role, selected)
            if role == AgentRole.ANALYSIS:
                current_stage["name"] = "analysis"
                self.repository.transition(
                    task_id, TaskStatus.ANALYZING, "analysis",
                    "正在逐篇提取方法、实验、创新点和局限", 35,
                )
            elif role == AgentRole.COMPARISON:
                current_stage["name"] = "comparison"
                self.repository.transition(
                    task_id, TaskStatus.ANALYZING, "comparison",
                    "正在归一化字段并融合跨文献比较", 50,
                )
            elif role == AgentRole.WRITING:
                current_stage["name"] = "writing"
                self.repository.transition(
                    task_id, TaskStatus.WRITING, "writing",
                    "正在依据 RAG 证据片段撰写四章节报告", 65,
                )

        def on_finish(role: AgentRole, output: Any) -> None:
            finished_roles.add(role)
            payload = _output_payload(output)
            output_ref = {
                AgentRole.RETRIEVAL: "evidence_pack",
                AgentRole.ANALYSIS: "artifact:analysis",
                AgentRole.COMPARISON: "artifact:comparison",
                AgentRole.WRITING: "draft",
            }[role]
            self.repository.finish_agent(
                task_id, role, AgentStatus.SUCCEEDED,
                output_ref=output_ref, payload=payload,
            )
            if role == AgentRole.ANALYSIS:
                model = _get_model(output)
                if model is not None:
                    self.repository.save_artifact(task_id, "analysis", model)
            elif role == AgentRole.COMPARISON:
                model = _get_model(output)
                if model is not None:
                    self.repository.save_artifact(task_id, "comparison", model)

        try:
            pack: EvidencePack = self.repository.get_evidence_pack(task_id, owner_session)
            result: ReviewRunResult = self.runner.run(
                task_id, pack, on_start=on_start, on_finish=on_finish
            )
            self.repository.save_artifact(task_id, "analysis", result.analysis)
            self.repository.save_artifact(task_id, "comparison", result.comparison)
            self.repository.transition(
                task_id, TaskStatus.VALIDATING, "validation",
                "正在检查四章节、引用解析、证据归属与语义支持提示", 85,
            )
            report, validation_warnings = prepare_report(
                task_id, pack, result.draft, CitationValidator()
            )
            report_id = self.repository.save_report(task_id, report, owner_session)
            if validation_warnings:
                current = self.repository.get_task_raw(task_id, owner_session)
                warnings = json_loads(current["warnings_json"], [])
                warnings.extend(item for item in validation_warnings if item not in warnings)
                self.repository.set_task_metadata(task_id, warnings=warnings)
            self.repository.transition(
                task_id, TaskStatus.COMPLETED, "completed",
                "结构、章节与引用均通过检查；报告已完成，仍需领域评审员抽查语义支持",
                100, report_id=report_id,
            )
        except ReportValidationError as exc:
            self._fail_running_agents(task_id, started_roles - finished_roles, str(exc))
            self.repository.fail_task(
                task_id, "validation",
                "一次校正后仍存在悬空引用、错配引用或章节缺失，报告未发布：" + str(exc),
            )
        except Exception as exc:
            logger.exception("Generation failed for %s", task_id)
            self._fail_running_agents(task_id, started_roles - finished_roles, str(exc))
            self.repository.fail_task(task_id, current_stage["name"], f"生成阶段失败：{exc}")

    def _fail_running_agents(self, task_id: str, roles: set[AgentRole], error: str) -> None:
        for role in roles:
            try:
                self.repository.finish_agent(task_id, role, AgentStatus.FAILED, error=error)
            except Exception:
                logger.exception("Could not mark agent %s failed for %s", role, task_id)


def _get_model(output: Any) -> Any | None:
    value = getattr(output, "pydantic", None)
    return value if value is not None else None


def _output_payload(output: Any) -> Any:
    value = getattr(output, "pydantic", None)
    if value is not None:
        return value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    raw = getattr(output, "raw", None)
    if raw is not None:
        return str(raw)[:10000]
    if hasattr(output, "model_dump"):
        return output.model_dump(mode="json")
    return str(output)[:10000]
