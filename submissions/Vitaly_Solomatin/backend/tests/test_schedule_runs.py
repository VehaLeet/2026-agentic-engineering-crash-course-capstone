"""Планові запуски в живому lifespan застосунку на тестовому Postgres."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import select

from app.api.app import create_app
from app.scheduling import JOB_ID
from app.settings import ScheduleSettingsStore
from app.storage.models import CollectionRun
from tests.test_api import GateSource
from tests.test_collection import Q3, q3_file

UTC = timezone.utc
MONDAY_MORNING = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)


@asynccontextmanager
async def scheduled_app(engine, source, *, enabled=True, now=lambda: MONDAY_MORNING, notifier=None):
    from app.storage.database import make_session_factory

    await ScheduleSettingsStore(make_session_factory(engine)).update(enabled, 60)
    app = create_app(engine=engine, source=source, now=now, notifier=notifier)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield app, client


async def runs(sessions, trigger="scheduled") -> list[CollectionRun]:
    async with sessions() as s:
        q = select(CollectionRun).where(CollectionRun.trigger == trigger).order_by(CollectionRun.id)
        return list((await s.execute(q)).scalars())


async def wait_for(check, timeout=5):
    async with asyncio.timeout(timeout):
        while not (result := await check()):
            await asyncio.sleep(0.02)
    return result


async def finished(sessions, trigger="scheduled"):
    rows = await runs(sessions, trigger)
    return [r for r in rows if r.status is not None]


def fire_now(app):
    app.state.scheduler._scheduler.get_job(JOB_ID).modify(next_run_time=datetime.now(UTC))


# 1. Стартовий запуск

async def test_first_scheduled_run_right_after_start(engine, sessions):
    async with scheduled_app(engine, GateSource({Q3: q3_file(2)})):
        [run] = await wait_for(lambda: finished(sessions))
    assert (run.trigger, run.status) == ("scheduled", "success")
    assert run.changed_days == [date(2026, 7, 1), date(2026, 7, 2)]


async def test_disabled_schedule_makes_no_runs(engine, sessions):
    async with scheduled_app(engine, GateSource({Q3: q3_file(2)}), enabled=False) as (app, _):
        await asyncio.sleep(0.3)
        assert app.state.scheduler.next_run_at() is None
    assert await runs(sessions) == []


# 2. Опорна дата

async def test_scheduled_reference_date_is_kyiv_today(engine, sessions):
    source = GateSource({Q3: q3_file(2)})
    async with scheduled_app(engine, source, now=lambda: datetime(2026, 9, 30, 22, 30, tzinfo=UTC)):
        await wait_for(lambda: finished(sessions))
    assert source.reference_dates == [date(2026, 10, 1)]


# 3. Неперекривання

async def test_tick_skipped_while_previous_scheduled_run_lasts(engine, sessions, caplog):
    source = GateSource({Q3: q3_file(2)}, gated=True)
    async with scheduled_app(engine, source) as (app, _):
        await source.entered.wait()
        with caplog.at_level(logging.WARNING, logger="apscheduler"):
            fire_now(app)
            await asyncio.sleep(0.3)
        assert len(await runs(sessions)) == 1
        assert "maximum number of running instances reached" in caplog.text
        source.gate.set()
        await wait_for(lambda: finished(sessions))
    assert len(await runs(sessions)) == 1


async def test_scheduled_run_during_manual_is_skipped_locked(engine, sessions):
    source = GateSource({Q3: q3_file(2)}, gated=True)
    async with scheduled_app(engine, source, enabled=False) as (app, client):
        assert (await client.post("/collect")).status_code == 202
        await source.entered.wait()
        await client.put("/settings/schedule", json={"enabled": True, "interval_minutes": 60})
        fire_now(app)
        [run] = await wait_for(lambda: finished(sessions))
        assert (run.trigger, run.status, run.error_message) == ("scheduled", "skipped_locked", None)
        source.gate.set()
        await app.state.manager.wait_all()
    [manual] = await runs(sessions, "manual")
    assert manual.status == "success"


# 4. Стійкість

async def test_source_failure_recorded_and_schedule_continues(engine, sessions):
    async with scheduled_app(engine, GateSource({Q3: q3_file(2)}, fail=True)) as (app, _):
        [run] = await wait_for(lambda: finished(sessions))
        assert app.state.scheduler.next_run_at() is not None
    assert (run.trigger, run.status) == ("scheduled", "error")
    assert "ОРЕЕ недоступний" in run.error_message


# 5. Сповіщення

class RecordingNotifier:
    def __init__(self):
        self.calls = []

    async def notify_run(self, run_id, changed, recalculated):
        self.calls.append((run_id, list(changed), list(recalculated)))


async def test_scheduled_success_notifies(engine, sessions):
    notifier = RecordingNotifier()
    async with scheduled_app(engine, GateSource({Q3: q3_file(2)}), notifier=notifier):
        [run] = await wait_for(lambda: finished(sessions))
    assert notifier.calls == [(run.id, [date(2026, 7, 1), date(2026, 7, 2)], [])]


# 6. Зупинка

async def test_shutdown_stops_schedule_and_leaves_trace(engine, sessions):
    source = GateSource({Q3: q3_file(2)}, gated=True)
    async with scheduled_app(engine, source) as (app, _):
        await source.entered.wait()
        scheduler = app.state.scheduler
    assert scheduler._scheduler.get_jobs() == [] and scheduler.next_run_at() is None
    [run] = await runs(sessions)
    assert run.status is None and run.finished_at is None
