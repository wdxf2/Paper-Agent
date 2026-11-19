from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, get_settings
from .models import (
    EVALUATION_DIMENSIONS,
    EVALUATION_SCALE_VERSION,
    AnalysisView,
    CandidateListView,
    ConfirmSelectionRequest,
    EvaluationRequest,
    EvaluationView,
    HealthView,
    ReportView,
    TaskCreateRequest,
    TaskStatus,
    TaskView,
)
from .repository import InvalidTransition, ReportNotFound, RepositoryError, TaskNotFound
from .service import ReviewService


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


def create_app(settings: Settings | None = None, service: ReviewService | None = None) -> FastAPI:
    settings = settings or get_settings()
    review_service = service or ReviewService(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        review_service.bootstrap()
        app.state.service = review_service
        try:
            yield
        finally:
            review_service.shutdown()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="基于 CrewAI 与可追溯 RAG 的科研文献智能综述生成系统",
        lifespan=lifespan,
    )
    app.state.service = review_service
    app.state.settings = settings

    @app.middleware("http")
    async def session_scope(request: Request, call_next):
        session_id = request.cookies.get(settings.session_cookie)
        new_session = not bool(session_id)
        if not session_id:
            session_id = secrets.token_urlsafe(32)
        request.state.session_id = session_id
        response = await call_next(request)
        if new_session:
            response.set_cookie(
                settings.session_cookie,
                session_id,
                httponly=True,
                samesite="lax",
                max_age=60 * 60 * 24 * 30,
            )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        fields: dict[str, str] = {}
        for error in exc.errors():
            location = ".".join(
                str(item)
                for item in error.get("loc", [])
                if item not in {"body", "query", "path"}
            )
            fields[location or "request"] = error.get("msg", "输入无效")
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_input",
                "message": "输入校验失败，请修正标记字段后重试",
                "fields": fields,
            },
        )

    @app.exception_handler(TaskNotFound)
    async def not_found_handler(request: Request, exc: TaskNotFound):
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "message": str(exc), "fields": {}},
        )

    @app.exception_handler(ReportNotFound)
    async def report_not_found_handler(request: Request, exc: ReportNotFound):
        return JSONResponse(
            status_code=404,
            content={"error": "report_not_found", "message": str(exc), "fields": {}},
        )

    @app.exception_handler(InvalidTransition)
    async def transition_handler(request: Request, exc: InvalidTransition):
        return JSONResponse(
            status_code=409,
            content={"error": "invalid_state", "message": str(exc), "fields": {}},
        )

    @app.exception_handler(RepositoryError)
    async def repository_handler(request: Request, exc: RepositoryError):
        return JSONResponse(
            status_code=400,
            content={"error": "business_rule", "message": str(exc), "fields": {}},
        )

    def session_id(request: Request) -> str:
        return request.state.session_id

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/v1/health", response_model=HealthView)
    def health() -> HealthView:
        return review_service.health()

    @app.get("/api/v1/meta/evaluation-scale")
    def evaluation_scale():
        return {
            "scale_version": EVALUATION_SCALE_VERSION,
            "dimensions": list(EVALUATION_DIMENSIONS),
            "score_range": [1, 5],
        }

    @app.post("/api/v1/tasks", response_model=TaskView, status_code=202)
    def create_task(request: TaskCreateRequest, http_request: Request) -> TaskView:
        return review_service.create_task(request, session_id(http_request))

    @app.get("/api/v1/tasks", response_model=list[TaskView])
    def list_tasks(http_request: Request) -> list[TaskView]:
        return review_service.list_tasks(session_id(http_request))

    @app.get("/api/v1/tasks/{task_id}", response_model=TaskView)
    def get_task(task_id: str, http_request: Request) -> TaskView:
        return review_service.get_task(task_id, session_id(http_request))

    @app.get("/api/v1/tasks/{task_id}/candidates", response_model=CandidateListView)
    def get_candidates(task_id: str, http_request: Request) -> CandidateListView:
        return review_service.get_candidates(task_id, session_id(http_request))

    @app.post("/api/v1/tasks/{task_id}/confirm", response_model=TaskView, status_code=202)
    def confirm_selection(
        task_id: str, request: ConfirmSelectionRequest, http_request: Request
    ) -> TaskView:
        return review_service.confirm_selection(task_id, request, session_id(http_request))

    @app.post("/api/v1/tasks/{task_id}/retry", response_model=TaskView, status_code=202)
    def retry_task(task_id: str, http_request: Request) -> TaskView:
        return review_service.retry_task(task_id, session_id(http_request))

    @app.get("/api/v1/tasks/{task_id}/analysis", response_model=AnalysisView)
    def get_analysis(task_id: str, http_request: Request) -> AnalysisView:
        return review_service.get_analysis(task_id, session_id(http_request))

    @app.get("/api/v1/tasks/{task_id}/report", response_model=ReportView)
    def get_task_report(task_id: str, http_request: Request) -> ReportView:
        return review_service.get_report(task_id, session_id(http_request))

    @app.get("/api/v1/reports/{report_id}", response_model=ReportView)
    def get_report(report_id: str, http_request: Request) -> ReportView:
        return review_service.get_report_by_id(report_id, session_id(http_request))

    @app.post("/api/v1/reports/{report_id}/evaluations", response_model=EvaluationView, status_code=201)
    def create_evaluation(
        report_id: str, request: EvaluationRequest, http_request: Request
    ) -> EvaluationView:
        return review_service.create_evaluation(report_id, request, session_id(http_request))

    @app.get("/api/v1/reports/{report_id}/evaluations", response_model=list[EvaluationView])
    def list_evaluations(report_id: str, http_request: Request) -> list[EvaluationView]:
        return review_service.list_evaluations(report_id, session_id(http_request))

    @app.get("/api/v1/tasks/{task_id}/events")
    async def stream_task_events(task_id: str, request: Request):
        owner = session_id(request)

        async def event_stream():
            last_revision: str | None = None
            while True:
                if await request.is_disconnected():
                    break
                try:
                    task = await asyncio.to_thread(review_service.get_task, task_id, owner)
                except TaskNotFound:
                    yield "event: error\ndata: {\"message\":\"task not found\"}\n\n"
                    break
                revision = task.updated_at.isoformat()
                if revision != last_revision:
                    last_revision = revision
                    yield f"event: task\ndata: {task.model_dump_json()}\n\n"
                if task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
                    break
                await asyncio.sleep(1.0)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
