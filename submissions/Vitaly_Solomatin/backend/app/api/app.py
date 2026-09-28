"""HTTP API: автентифікований ручний запуск збору, стан запусків, перевірка живості."""

import secrets
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.runs_manager import RunManager
from app.api.settings import ApiSettings
from app.collection.collect import collect_once
from app.collection.runs import RunInfo, RunLog
from app.dam_source.source import DamSource
from app.storage.repository import DamRepository
from app.timeutil import kyiv_today


class Run(BaseModel):
    id: int
    started_at: datetime
    finished_at: datetime | None
    status: str | None
    trigger: str
    changed_days: list[date]
    error_message: str | None

    @classmethod
    def of(cls, info: RunInfo) -> "Run":
        return cls(id=info.id, started_at=info.started_at, finished_at=info.finished_at, status=info.status,
                   trigger=info.trigger, changed_days=list(info.changed_days), error_message=info.error_message)


class CollectAccepted(BaseModel):
    run_id: int
    status_url: str


class SystemStatus(BaseModel):
    last_run: Run | None
    last_update: Run | None
    recent_errors: list[Run]


_basic = HTTPBasic(auto_error=False)


def _require_auth(settings: ApiSettings):
    expected_user = settings.username.encode()
    expected_password = settings.password.encode()

    def check(credentials: Annotated[HTTPBasicCredentials | None, Depends(_basic)]) -> None:
        if credentials is not None:
            # Обидва порівняння виконуються завжди: час відповіді не видає, що саме хибне.
            user_ok = secrets.compare_digest(credentials.username.encode(), expected_user)
            password_ok = secrets.compare_digest(credentials.password.encode(), expected_password)
            if user_ok & password_ok:
                return
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required",
                            headers={"WWW-Authenticate": 'Basic realm="oree-dam-monitor"'})

    return check


def create_app(
    settings: ApiSettings | None = None,
    engine: AsyncEngine | None = None,
    source: DamSource | None = None,
    now: Callable[[], datetime | None] = lambda: None,
) -> FastAPI:
    """Без кредів у налаштуваннях чи в env застосунок не будується (закрито за замовчуванням)."""
    settings = settings or ApiSettings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from app.dam_source.source import OreeDamSource
        from app.storage.database import make_engine, make_session_factory

        own_engine = engine is None
        db = engine or make_engine()
        sessions = make_session_factory(db)
        runs = RunLog(sessions)
        repository = DamRepository(sessions)
        dam_source = source or OreeDamSource()

        async def job(run_id: int):
            return await collect_once(dam_source, repository, runs, db, kyiv_today(now()), "manual", run_id)

        app.state.runs = runs
        app.state.manager = RunManager(job)
        try:
            yield
        finally:
            await app.state.manager.shutdown()
            if own_engine:
                await db.dispose()

    # /docs, /redoc і /openapi.json вимкнено: інакше вони відкриті без автентифікації.
    app = FastAPI(title="OREE DAM Monitor", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # Автентифікація на рівні роутера: новий маршрут не лишиться відкритим випадково.
    api = APIRouter(dependencies=[Depends(_require_auth(settings))])

    @api.post("/collect", status_code=status.HTTP_202_ACCEPTED, response_model=CollectAccepted)
    async def collect(request: Request, response: Response) -> CollectAccepted:
        run_id = await request.app.state.runs.start("manual")
        request.app.state.manager.start(run_id)
        response.headers["Location"] = f"/runs/{run_id}"
        return CollectAccepted(run_id=run_id, status_url=f"/runs/{run_id}")

    @api.get("/runs/{run_id}", response_model=Run)
    async def get_run(run_id: int, request: Request) -> Run:
        info = await request.app.state.runs.find(run_id)
        if info is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
        return Run.of(info)

    @api.get("/status", response_model=SystemStatus)
    async def get_status(request: Request) -> SystemStatus:
        state = await request.app.state.runs.state()
        return SystemStatus(
            last_run=state.last_run and Run.of(state.last_run),
            last_update=state.last_update and Run.of(state.last_update),
            recent_errors=[Run.of(r) for r in state.recent_errors],
        )

    app.include_router(api)
    app.state.protected_router = api  # для перевірки, що кожен маршрут під автентифікацією
    return app
