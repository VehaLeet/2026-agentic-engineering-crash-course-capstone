"""Журнал запусків збору. Пише окремими транзакціями, щоб переживати відкат основної."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.storage.models import RUN_STATUSES, RUN_TRIGGERS, CollectionRun


@dataclass(frozen=True, slots=True)
class RunInfo:
    id: int
    started_at: datetime
    finished_at: datetime | None
    status: str | None
    trigger: str
    changed_days: tuple[date, ...]
    error_message: str | None


@dataclass(frozen=True, slots=True)
class RunState:
    last_run: RunInfo | None  # будь-який статус, включно з незавершеним
    last_update: RunInfo | None  # останній success — дані справді змінились
    recent_errors: tuple[RunInfo, ...]


def _info(run: CollectionRun) -> RunInfo:
    return RunInfo(run.id, run.started_at, run.finished_at, run.status, run.trigger,
                   tuple(run.changed_days or ()), run.error_message)


class RunLog:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def start(self, trigger: str) -> int:
        if trigger not in RUN_TRIGGERS:
            raise ValueError(f"невідомий спосіб запуску {trigger!r}")
        async with self.sessions() as session, session.begin():
            run = CollectionRun(started_at=datetime.now(timezone.utc), trigger=trigger)
            session.add(run)
            await session.flush()
            return run.id

    async def finish(
        self, run_id: int, status: str, changed_days: Iterable[date] = (), error_message: str | None = None
    ) -> None:
        if status not in RUN_STATUSES:
            raise ValueError(f"невідомий статус {status!r}")
        async with self.sessions() as session, session.begin():
            await session.execute(
                update(CollectionRun).where(CollectionRun.id == run_id).values(
                    status=status, finished_at=datetime.now(timezone.utc),
                    changed_days=sorted(changed_days), error_message=error_message,
                )
            )

    async def get(self, run_id: int) -> RunInfo:
        async with self.sessions() as session:
            return _info(await session.get_one(CollectionRun, run_id))

    async def state(self, errors_limit: int = 5) -> RunState:
        async with self.sessions() as session:
            newest = select(CollectionRun).order_by(desc(CollectionRun.started_at), desc(CollectionRun.id))
            last_run = (await session.execute(newest.limit(1))).scalar_one_or_none()
            last_update = (await session.execute(
                newest.where(CollectionRun.status == "success").limit(1)
            )).scalar_one_or_none()
            errors = (await session.execute(
                newest.where(CollectionRun.status == "error").limit(errors_limit)
            )).scalars().all()
        return RunState(
            last_run and _info(last_run), last_update and _info(last_update), tuple(_info(e) for e in errors)
        )
