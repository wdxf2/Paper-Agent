from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    TASK_STATUS_LABELS,
    AgentRole,
    AgentStatus,
    AgentTaskView,
    AnalysisArtifact,
    CandidateListView,
    ComparisonArtifact,
    EvaluationRequest,
    EvaluationView,
    EvidenceFragment,
    EvidencePack,
    PaperCandidate,
    PaperEvidenceBundle,
    ReportView,
    SearchPlan,
    SourceName,
    TaskCreateRequest,
    TaskEventView,
    TaskStatus,
    TaskView,
)
from .text import json_dumps, json_loads


TERMINAL_STATUSES = {TaskStatus.COMPLETED, TaskStatus.FAILED}
ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.RETRIEVING, TaskStatus.FAILED},
    TaskStatus.RETRIEVING: {TaskStatus.AWAITING_CONFIRMATION, TaskStatus.FAILED},
    TaskStatus.AWAITING_CONFIRMATION: {TaskStatus.ANALYZING, TaskStatus.FAILED},
    TaskStatus.ANALYZING: {TaskStatus.WRITING, TaskStatus.FAILED},
    TaskStatus.WRITING: {TaskStatus.VALIDATING, TaskStatus.FAILED},
    TaskStatus.VALIDATING: {TaskStatus.COMPLETED, TaskStatus.FAILED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
}


class RepositoryError(RuntimeError):
    pass


class TaskNotFound(RepositoryError):
    pass


class ReportNotFound(RepositoryError):
    pass


class InvalidTransition(RepositoryError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class Repository:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def init_db(self) -> None:
        with self.connect() as connection:
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
            }
            if columns and "keywords_json" not in columns:
                connection.execute(
                    "ALTER TABLE tasks ADD COLUMN keywords_json TEXT NOT NULL DEFAULT '[]'"
                )
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    parent_task_id TEXT,
                    owner_session TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    year_start INTEGER NOT NULL,
                    year_end INTEGER NOT NULL,
                    sources_json TEXT NOT NULL,
                    keywords_json TEXT NOT NULL DEFAULT '[]',
                    candidate_limit INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    error_stage TEXT,
                    error_message TEXT,
                    warnings_json TEXT NOT NULL DEFAULT '[]',
                    source_mode TEXT NOT NULL DEFAULT 'live',
                    selected_paper_ids_json TEXT NOT NULL DEFAULT '[]',
                    report_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    confirmed_at TEXT,
                    completed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS task_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS papers (
                    paper_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    year INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS task_papers (
                    task_id TEXT NOT NULL,
                    paper_id TEXT NOT NULL,
                    selected INTEGER NOT NULL DEFAULT 0,
                    ordinal INTEGER NOT NULL,
                    PRIMARY KEY (task_id, paper_id)
                );

                CREATE TABLE IF NOT EXISTS evidence (
                    task_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    paper_id TEXT NOT NULL,
                    quote TEXT NOT NULL,
                    locator TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    PRIMARY KEY (task_id, evidence_id)
                );

                CREATE TABLE IF NOT EXISTS agent_tasks (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_ref TEXT,
                    output_ref TEXT,
                    error TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    payload_json TEXT,
                    UNIQUE (task_id, role)
                );

                CREATE TABLE IF NOT EXISTS artifacts (
                    task_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (task_id, kind)
                );

                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evaluations (
                    id TEXT PRIMARY KEY,
                    report_id TEXT NOT NULL,
                    reviewer_id TEXT NOT NULL,
                    scale_version TEXT NOT NULL,
                    scores_json TEXT NOT NULL,
                    comments TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_owner ON tasks(owner_session, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id, event_id);
                CREATE INDEX IF NOT EXISTS idx_task_papers_task ON task_papers(task_id, ordinal);
                CREATE INDEX IF NOT EXISTS idx_evidence_task ON evidence(task_id, paper_id);
                CREATE INDEX IF NOT EXISTS idx_agent_tasks_task ON agent_tasks(task_id, role);
                CREATE INDEX IF NOT EXISTS idx_reports_task ON reports(task_id);
                CREATE INDEX IF NOT EXISTS idx_evaluations_report ON evaluations(report_id, created_at DESC);
                """
            )

    def create_task(
        self,
        request: TaskCreateRequest,
        owner_session: str,
        parent_task_id: str | None = None,
    ) -> TaskView:
        task_id = "task_" + uuid.uuid4().hex[:16]
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    id, parent_task_id, owner_session, topic, year_start, year_end,
                    sources_json, keywords_json, candidate_limit, status, progress, warnings_json,
                    source_mode, selected_paper_ids_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    parent_task_id,
                    owner_session,
                    request.topic,
                    request.year_start,
                    request.year_end,
                    json_dumps([source.value for source in request.sources]),
                    json_dumps(request.keywords),
                    request.candidate_limit,
                    TaskStatus.PENDING.value,
                    0,
                    "[]",
                    "live",
                    "[]",
                    now,
                    now,
                ),
            )
            self._insert_event(connection, task_id, "created", TaskStatus.PENDING, "任务已创建", now)
            for role in AgentRole:
                connection.execute(
                    "INSERT INTO agent_tasks (id, task_id, role, status) VALUES (?, ?, ?, ?)",
                    ("agt_" + uuid.uuid4().hex[:12], task_id, role.value, AgentStatus.PENDING.value),
                )
        return self.get_task(task_id, owner_session)

    def list_tasks(self, owner_session: str) -> list[TaskView]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id FROM tasks WHERE owner_session = ? ORDER BY created_at DESC",
                (owner_session,),
            ).fetchall()
        return [self.get_task(row["id"], owner_session) for row in rows]

    def get_task(self, task_id: str, owner_session: str | None = None) -> TaskView:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                raise TaskNotFound(f"任务 {task_id} 不存在")
            if owner_session is not None and row["owner_session"] != owner_session:
                raise TaskNotFound(f"任务 {task_id} 不存在")
            agent_rows = connection.execute(
                "SELECT * FROM agent_tasks WHERE task_id = ? ORDER BY rowid", (task_id,)
            ).fetchall()
            event_rows = connection.execute(
                "SELECT * FROM task_events WHERE task_id = ? ORDER BY event_id", (task_id,)
            ).fetchall()
        return self._task_view_from_row(row, agent_rows, event_rows)

    def get_task_raw(self, task_id: str, owner_session: str | None = None) -> sqlite3.Row:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None or (owner_session is not None and row["owner_session"] != owner_session):
            raise TaskNotFound(f"任务 {task_id} 不存在")
        return row

    def set_task_metadata(
        self, task_id: str, warnings: list[str] | None = None, source_mode: str | None = None
    ) -> None:
        fields: list[str] = []
        values: list[object] = []
        if warnings is not None:
            fields.append("warnings_json = ?")
            values.append(json_dumps(warnings))
        if source_mode is not None:
            fields.append("source_mode = ?")
            values.append(source_mode)
        fields.append("updated_at = ?")
        values.append(utc_now())
        values.append(task_id)
        with self.connect() as connection:
            connection.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", values)

    def transition(
        self,
        task_id: str,
        new_status: TaskStatus,
        stage: str,
        message: str,
        progress: int,
        *,
        error_stage: str | None = None,
        error_message: str | None = None,
        report_id: str | None = None,
    ) -> None:
        now = utc_now()
        with self.connect() as connection:
            row = connection.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                raise TaskNotFound(f"任务 {task_id} 不存在")
            current = TaskStatus(row["status"])
            if new_status != current and new_status not in ALLOWED_TRANSITIONS[current]:
                raise InvalidTransition(f"非法状态迁移：{current.value} -> {new_status.value}")
            assignments = [
                "status = ?", "progress = ?", "updated_at = ?", "error_stage = ?", "error_message = ?"
            ]
            values: list[object] = [
                new_status.value, max(0, min(100, int(progress))), now, error_stage, error_message
            ]
            if new_status == TaskStatus.ANALYZING:
                assignments.append("confirmed_at = ?")
                values.append(now)
            if new_status == TaskStatus.COMPLETED:
                assignments.append("completed_at = ?")
                values.append(now)
            if report_id is not None:
                assignments.append("report_id = ?")
                values.append(report_id)
            values.append(task_id)
            connection.execute(f"UPDATE tasks SET {', '.join(assignments)} WHERE id = ?", values)
            self._insert_event(connection, task_id, stage, new_status, message, now)

    def fail_task(self, task_id: str, stage: str, message: str) -> None:
        row = self.get_task_raw(task_id)
        current = TaskStatus(row["status"])
        if current == TaskStatus.FAILED:
            return
        self.transition(
            task_id, TaskStatus.FAILED, stage, message, int(row["progress"]),
            error_stage=stage, error_message=message,
        )

    def save_candidates(
        self,
        task_id: str,
        papers: Iterable[PaperCandidate],
        evidence: Iterable[EvidenceFragment],
        warnings: list[str],
        source_mode: str,
    ) -> None:
        now = utc_now()
        with self.connect() as connection:
            for ordinal, paper in enumerate(papers):
                payload = paper.model_dump(mode="json")
                connection.execute(
                    """
                    INSERT INTO papers (paper_id, title, year, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(paper_id) DO UPDATE SET
                        title = excluded.title, year = excluded.year, payload_json = excluded.payload_json
                    """,
                    (paper.paper_id, paper.title, paper.year, json_dumps(payload), now),
                )
                connection.execute(
                    """
                    INSERT INTO task_papers (task_id, paper_id, selected, ordinal)
                    VALUES (?, ?, 0, ?)
                    ON CONFLICT(task_id, paper_id) DO UPDATE SET ordinal = excluded.ordinal
                    """,
                    (task_id, paper.paper_id, ordinal),
                )
            for fragment in evidence:
                connection.execute(
                    """
                    INSERT INTO evidence (task_id, evidence_id, paper_id, quote, locator, scope)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id, fragment.evidence_id, fragment.paper_id, fragment.quote,
                        fragment.locator, fragment.scope.value,
                    ),
                )
            connection.execute(
                "UPDATE tasks SET warnings_json = ?, source_mode = ?, updated_at = ? WHERE id = ?",
                (json_dumps(warnings), source_mode, now, task_id),
            )

    def list_candidates(self, task_id: str, owner_session: str) -> CandidateListView:
        task = self.get_task_raw(task_id, owner_session)
        search_plan = self.get_artifact(task_id, "search_plan")
        search_meta = self.get_artifact(task_id, "search_meta") or {}
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT p.payload_json, COUNT(e.evidence_id) AS evidence_count
                FROM task_papers tp
                JOIN papers p ON p.paper_id = tp.paper_id
                LEFT JOIN evidence e ON e.task_id = tp.task_id AND e.paper_id = tp.paper_id
                WHERE tp.task_id = ?
                GROUP BY p.paper_id, tp.ordinal
                ORDER BY tp.ordinal
                """,
                (task_id,),
            ).fetchall()
        candidates: list[PaperCandidate] = []
        for row in rows:
            payload = json_loads(row["payload_json"], {})
            payload["evidence_count"] = int(row["evidence_count"] or 0)
            payload["has_evidence"] = payload["evidence_count"] > 0
            candidates.append(PaperCandidate.model_validate(payload))
        return CandidateListView(
            task_id=task_id,
            topic=task["topic"],
            status=TaskStatus(task["status"]),
            source_mode=task["source_mode"],
            warnings=json_loads(task["warnings_json"], []),
            search_plan=SearchPlan.model_validate(search_plan) if search_plan else None,
            screening_mode=str(search_meta.get("screening_mode", "heuristic")),
            candidates=candidates,
        )

    def confirm_selection(self, task_id: str, paper_ids: list[str], owner_session: str) -> list[str]:
        task = self.get_task_raw(task_id, owner_session)
        if TaskStatus(task["status"]) != TaskStatus.AWAITING_CONFIRMATION:
            raise InvalidTransition("只有等待文献确认的任务可以固定选择快照")
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT tp.paper_id, COUNT(e.evidence_id) AS evidence_count
                FROM task_papers tp
                LEFT JOIN evidence e ON e.task_id = tp.task_id AND e.paper_id = tp.paper_id
                WHERE tp.task_id = ?
                GROUP BY tp.paper_id
                """,
                (task_id,),
            ).fetchall()
            valid = {row["paper_id"]: int(row["evidence_count"] or 0) for row in rows}
            unknown = [paper_id for paper_id in paper_ids if paper_id not in valid]
            if unknown:
                raise RepositoryError(f"确认集合包含未知文献：{', '.join(unknown)}")
            without_evidence = [paper_id for paper_id in paper_ids if valid[paper_id] <= 0]
            if without_evidence:
                raise RepositoryError("至少一篇已选文献必须具备可用证据；当前选择包含无证据文献")
            now = utc_now()
            connection.execute("UPDATE task_papers SET selected = 0 WHERE task_id = ?", (task_id,))
            connection.executemany(
                "UPDATE task_papers SET selected = 1 WHERE task_id = ? AND paper_id = ?",
                [(task_id, paper_id) for paper_id in paper_ids],
            )
            connection.execute(
                "UPDATE tasks SET selected_paper_ids_json = ?, confirmed_at = ?, updated_at = ? WHERE id = ?",
                (json_dumps(paper_ids), now, now, task_id),
            )
        return paper_ids

    def get_evidence_pack(self, task_id: str, owner_session: str) -> EvidencePack:
        task = self.get_task_raw(task_id, owner_session)
        selected_ids = json_loads(task["selected_paper_ids_json"], [])
        if not selected_ids:
            raise RepositoryError("尚未确认文献选择快照")
        with self.connect() as connection:
            paper_rows = connection.execute(
                """
                SELECT p.payload_json
                FROM task_papers tp JOIN papers p ON p.paper_id = tp.paper_id
                WHERE tp.task_id = ? AND tp.selected = 1
                ORDER BY tp.ordinal
                """,
                (task_id,),
            ).fetchall()
            evidence_rows = connection.execute(
                "SELECT * FROM evidence WHERE task_id = ? ORDER BY paper_id, evidence_id",
                (task_id,),
            ).fetchall()
        papers = [PaperCandidate.model_validate(json_loads(row["payload_json"], {})) for row in paper_rows]
        selected_set = set(selected_ids)
        evidence = [
            EvidenceFragment(
                evidence_id=row["evidence_id"],
                paper_id=row["paper_id"],
                quote=row["quote"],
                locator=row["locator"],
                scope=row["scope"],
            )
            for row in evidence_rows
            if row["paper_id"] in selected_set
        ]
        ids_by_paper: dict[str, list[str]] = {}
        for fragment in evidence:
            ids_by_paper.setdefault(fragment.paper_id, []).append(fragment.evidence_id)
        bundles = [
            PaperEvidenceBundle(paper=paper, evidence_ids=ids_by_paper.get(paper.paper_id, []))
            for paper in papers
        ]
        notes = [
            "证据仅来自当前可获取且可定位的摘要或全文片段。",
            "未取得全文时，报告不得宣称已审阅全文，也不得补造实验数值。",
        ]
        if task["source_mode"] == "demo":
            notes.append("当前为受控测试语料模式，内容只用于流程验收。")
        return EvidencePack(
            topic=task["topic"],
            year_start=int(task["year_start"]),
            year_end=int(task["year_end"]),
            papers=bundles,
            evidence=evidence,
            coverage_notes=notes,
        )

    def save_artifact(self, task_id: str, kind: str, model: object) -> None:
        payload = model.model_dump(mode="json") if hasattr(model, "model_dump") else model
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO artifacts (task_id, kind, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id, kind) DO UPDATE SET
                    payload_json = excluded.payload_json, created_at = excluded.created_at
                """,
                (task_id, kind, json_dumps(payload), utc_now()),
            )

    def get_artifact(self, task_id: str, kind: str, owner_session: str | None = None) -> object | None:
        if owner_session is not None:
            self.get_task_raw(task_id, owner_session)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM artifacts WHERE task_id = ? AND kind = ?",
                (task_id, kind),
            ).fetchone()
        return json_loads(row["payload_json"], None) if row else None

    def get_analysis_view(
        self, task_id: str, owner_session: str
    ) -> tuple[AnalysisArtifact, ComparisonArtifact]:
        analysis_raw = self.get_artifact(task_id, "analysis", owner_session)
        comparison_raw = self.get_artifact(task_id, "comparison", owner_session)
        if analysis_raw is None or comparison_raw is None:
            raise RepositoryError("分析结果尚未生成")
        return AnalysisArtifact.model_validate(analysis_raw), ComparisonArtifact.model_validate(comparison_raw)

    def save_report(self, task_id: str, report: ReportView, owner_session: str) -> str:
        self.get_task_raw(task_id, owner_session)
        report_id = report.report_id or "rep_" + uuid.uuid4().hex[:16]
        report = report.model_copy(update={"report_id": report_id})
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO reports (id, task_id, title, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (report_id, task_id, report.title, json_dumps(report.model_dump(mode="json")), now),
            )
            connection.execute(
                "UPDATE tasks SET report_id = ?, updated_at = ? WHERE id = ?",
                (report_id, now, task_id),
            )
        return report_id

    def get_report(self, report_id: str, owner_session: str) -> ReportView:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT r.payload_json FROM reports r JOIN tasks t ON t.id = r.task_id
                WHERE r.id = ? AND t.owner_session = ?
                """,
                (report_id, owner_session),
            ).fetchone()
        if row is None:
            raise ReportNotFound(f"报告 {report_id} 不存在")
        return ReportView.model_validate(json_loads(row["payload_json"], {}))

    def get_report_for_task(
        self, task_id: str, owner_session: str, *, require_completed: bool = True
    ) -> ReportView:
        task = self.get_task_raw(task_id, owner_session)
        if require_completed and TaskStatus(task["status"]) != TaskStatus.COMPLETED:
            raise RepositoryError("任务尚未完成，不能读取正式报告")
        if not task["report_id"]:
            raise ReportNotFound(f"任务 {task_id} 尚无报告")
        return self.get_report(task["report_id"], owner_session)

    def create_evaluation(
        self, report_id: str, evaluation: EvaluationRequest, owner_session: str
    ) -> EvaluationView:
        self.get_report(report_id, owner_session)
        evaluation_id = "eval_" + uuid.uuid4().hex[:16]
        created_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO evaluations (
                    id, report_id, reviewer_id, scale_version, scores_json, comments, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation_id, report_id, evaluation.reviewer_id, evaluation.scale_version,
                    json_dumps(evaluation.scores), evaluation.comments, created_at,
                ),
            )
        return EvaluationView(
            evaluation_id=evaluation_id,
            report_id=report_id,
            reviewer_id=evaluation.reviewer_id,
            scale_version=evaluation.scale_version,
            scores=evaluation.scores,
            comments=evaluation.comments,
            created_at=datetime.fromisoformat(created_at),
        )

    def list_evaluations(self, report_id: str, owner_session: str) -> list[EvaluationView]:
        self.get_report(report_id, owner_session)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM evaluations WHERE report_id = ? ORDER BY created_at DESC",
                (report_id,),
            ).fetchall()
        return [
            EvaluationView(
                evaluation_id=row["id"],
                report_id=row["report_id"],
                reviewer_id=row["reviewer_id"],
                scale_version=row["scale_version"],
                scores=json_loads(row["scores_json"], {}),
                comments=row["comments"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def start_agent(self, task_id: str, role: AgentRole, input_ref: str | None = None) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE agent_tasks
                SET status = ?, input_ref = ?, started_at = COALESCE(started_at, ?), error = NULL
                WHERE task_id = ? AND role = ?
                """,
                (AgentStatus.RUNNING.value, input_ref, now, task_id, role.value),
            )

    def finish_agent(
        self,
        task_id: str,
        role: AgentRole,
        status: AgentStatus,
        *,
        output_ref: str | None = None,
        error: str | None = None,
        payload: object | None = None,
    ) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE agent_tasks
                SET status = ?, output_ref = ?, error = ?, finished_at = ?, payload_json = ?
                WHERE task_id = ? AND role = ?
                """,
                (
                    status.value, output_ref, error, now,
                    json_dumps(payload) if payload is not None else None,
                    task_id, role.value,
                ),
            )
            connection.execute("UPDATE tasks SET updated_at = ? WHERE id = ?", (now, task_id))

    def mark_stale_tasks(self) -> int:
        stale = [
            TaskStatus.RETRIEVING.value,
            TaskStatus.ANALYZING.value,
            TaskStatus.WRITING.value,
            TaskStatus.VALIDATING.value,
        ]
        placeholders = ",".join("?" for _ in stale)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT id FROM tasks WHERE status IN ({placeholders})", stale
            ).fetchall()
        for row in rows:
            try:
                self.fail_task(
                    row["id"], "startup", "服务重启导致未完成任务中断；请重试创建新任务"
                )
            except RepositoryError:
                continue
        return len(rows)

    def create_retry_task(self, original_task_id: str, owner_session: str) -> TaskView:
        row = self.get_task_raw(original_task_id, owner_session)
        request = TaskCreateRequest(
            topic=row["topic"],
            year_start=int(row["year_start"]),
            year_end=int(row["year_end"]),
            keywords=json_loads(row["keywords_json"], []),
            sources=[SourceName(item) for item in json_loads(row["sources_json"], [])],
            candidate_limit=int(row["candidate_limit"]),
        )
        return self.create_task(request, owner_session, parent_task_id=original_task_id)

    def _task_view_from_row(
        self,
        row: sqlite3.Row,
        agent_rows: list[sqlite3.Row],
        event_rows: list[sqlite3.Row],
    ) -> TaskView:
        status = TaskStatus(row["status"])
        agents = [
            AgentTaskView(
                agent_task_id=item["id"],
                task_id=item["task_id"],
                role=AgentRole(item["role"]),
                status=AgentStatus(item["status"]),
                input_ref=item["input_ref"],
                output_ref=item["output_ref"],
                error=item["error"],
                started_at=_parse_dt(item["started_at"]),
                finished_at=_parse_dt(item["finished_at"]),
            )
            for item in agent_rows
        ]
        events = [
            TaskEventView(
                event_id=item["event_id"],
                stage=item["stage"],
                status=TaskStatus(item["status"]),
                message=item["message"],
                created_at=datetime.fromisoformat(item["created_at"]),
            )
            for item in event_rows
        ]
        return TaskView(
            task_id=row["id"],
            parent_task_id=row["parent_task_id"],
            topic=row["topic"],
            year_start=int(row["year_start"]),
            year_end=int(row["year_end"]),
            keywords=json_loads(row["keywords_json"], []),
            sources=[SourceName(item) for item in json_loads(row["sources_json"], [])],
            candidate_limit=int(row["candidate_limit"]),
            status=status,
            stage_label=TASK_STATUS_LABELS[status],
            progress=int(row["progress"]),
            error_stage=row["error_stage"],
            error_message=row["error_message"],
            warnings=json_loads(row["warnings_json"], []),
            source_mode=row["source_mode"],
            selected_paper_ids=json_loads(row["selected_paper_ids_json"], []),
            report_id=row["report_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            confirmed_at=_parse_dt(row["confirmed_at"]),
            completed_at=_parse_dt(row["completed_at"]),
            agents=agents,
            events=events,
        )

    @staticmethod
    def _insert_event(
        connection: sqlite3.Connection,
        task_id: str,
        stage: str,
        status: TaskStatus,
        message: str,
        created_at: str,
    ) -> None:
        connection.execute(
            "INSERT INTO task_events (task_id, stage, status, message, created_at) VALUES (?, ?, ?, ?, ?)",
            (task_id, stage, status.value, message, created_at),
        )
