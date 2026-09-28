"""HTTP API: ручний запуск збору, стан запусків, ціни, перевірка живості.

Автентифікації немає свідомо (ранній MVP): межа доступу — loopback, див. app/api/__main__.py.
"""

from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.runs_manager import RunManager
from app.collection.collect import collect_once
from app.collection.runs import RunInfo, RunLog
from app.dam_source.source import DamSource
from app.notify.notifier import Notifier, notifier_from_env
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


HOURLY_RANGE_LIMIT_DAYS = 366  # рівно рік з високосним: ≤ 9 150 точок, ≈ 0.5 МБ

HOURLY_FIELDS = ("price", "volume_sell", "volume_buy", "declared_volume_sell", "declared_volume_buy")
DAILY_FIELDS = ("price_min", "price_max", "price_avg", "price_weighted",
                "volume_sell", "volume_buy", "declared_volume_sell", "declared_volume_buy", "periods")


def _column(values) -> list:
    # Decimal -> JSON-число лише на межі серіалізації; None лишається null.
    return [float(v) if v is not None and not isinstance(v, int) else v for v in values]


def create_app(
    engine: AsyncEngine | None = None,
    source: DamSource | None = None,
    now: Callable[[], datetime | None] = lambda: None,
    notifier: Notifier | None = None,
) -> FastAPI:

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

        dam_notifier = notifier or notifier_from_env(sessions, repository)

        async def job(run_id: int):
            return await collect_once(
                dam_source, repository, runs, db, kyiv_today(now()), "manual", run_id, notifier=dam_notifier
            )

        app.state.runs = runs
        app.state.repository = repository
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

    @app.post("/collect", status_code=status.HTTP_202_ACCEPTED, response_model=CollectAccepted)
    async def collect(request: Request, response: Response) -> CollectAccepted:
        run_id = await request.app.state.runs.start("manual")
        request.app.state.manager.start(run_id)
        response.headers["Location"] = f"/runs/{run_id}"
        return CollectAccepted(run_id=run_id, status_url=f"/runs/{run_id}")

    @app.get("/runs/{run_id}", response_model=Run)
    async def get_run(run_id: int, request: Request) -> Run:
        info = await request.app.state.runs.find(run_id)
        if info is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
        return Run.of(info)

    @app.get("/status", response_model=SystemStatus)
    async def get_status(request: Request) -> SystemStatus:
        state = await request.app.state.runs.state()
        return SystemStatus(
            last_run=state.last_run and Run.of(state.last_run),
            last_update=state.last_update and Run.of(state.last_update),
            recent_errors=[Run.of(r) for r in state.recent_errors],
        )

    @app.get("/prices")
    async def get_prices(
        request: Request,
        date_from: Annotated[date, Query()],
        date_to: Annotated[date, Query()],
        resolution: Annotated[Literal["hour", "day"], Query()] = "hour",
    ) -> dict:
        # Валідація до звернення до БД.
        if date_from > date_to:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "date_from must not be after date_to")
        body: dict = {"resolution": resolution, "date_from": date_from, "date_to": date_to}
        repository: DamRepository = request.app.state.repository
        if resolution == "hour":
            if (date_to - date_from).days + 1 > HOURLY_RANGE_LIMIT_DAYS:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    f"hourly range is limited to {HOURLY_RANGE_LIMIT_DAYS} days; use resolution=day",
                )
            rows = await repository.get_records(date_from, date_to)
            body["delivery_date"] = [r.delivery_date for r in rows]
            body["period"] = [r.period for r in rows]
            for field in HOURLY_FIELDS:
                body[field] = _column(getattr(r, field) for r in rows)
        else:
            days = await repository.get_daily(date_from, date_to)
            body["delivery_date"] = [d.delivery_date for d in days]
            for field in DAILY_FIELDS:
                body[field] = _column(getattr(d, field) for d in days)
        return body

    return app
