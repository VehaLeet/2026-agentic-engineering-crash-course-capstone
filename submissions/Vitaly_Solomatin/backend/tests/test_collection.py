import asyncio
import io
from datetime import date, timedelta

import pytest
from alembic import command
from sqlalchemy import func, inspect, select, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.backfill import run_locked_backfill
from app.collection.collect import collect_once
from app.collection.lock import DAM_WRITER_LOCK_KEY, dam_writer_lock
from app.collection.runs import RunLog
from app.dam_source.hashing import changed_days
from app.dam_source.models import FetchError, Quarter
from app.storage.models import CollectionRun, DamPrice, DamRawSnapshot
from app.storage.repository import DamRepository
from tests.fakes import FakeDamSource, csv_bytes

REF = date(2026, 9, 28)  # опорна дата в середині 2026Q3 -> тягнеться лише Q3
Q3 = Quarter(2026, 3)


def day_rows(day: date, price: str = "100.00") -> list[str]:
    return [f"{day:%d.%m.%Y};{p};{price};1.0;1.0;1.0;1.0" for p in range(1, 25)]


def q3_file(days: int = 2, changed: dict[date, str] | None = None) -> bytes:
    changed = changed or {}
    rows = []
    for i in range(days):
        d = date(2026, 7, 1) + timedelta(days=i)
        rows += day_rows(d, changed.get(d, "100.00"))
    return csv_bytes(*rows)


@pytest.fixture
def runs(sessions):
    return RunLog(sessions)


async def collect(source, repository, runs, engine, trigger="manual"):
    return await collect_once(source, repository, runs, engine, REF, trigger)


async def rows(sessions, model=DamPrice) -> int:
    async with sessions() as s:
        return (await s.execute(select(func.count()).select_from(model))).scalar_one()


@pytest.fixture
async def held_lock(database_url):
    """Утримує блокування з окремого процесу-«сусіда»: власний engine без пулу."""
    other = create_async_engine(database_url, poolclass=NullPool)
    conn = await other.connect()
    assert (await conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": DAM_WRITER_LOCK_KEY})).scalar_one()
    await conn.commit()
    yield
    await conn.close()
    await other.dispose()


# 1. Схема журналу

async def test_run_table_shape(engine):
    async with engine.connect() as conn:
        cols = await conn.run_sync(lambda c: {x["name"]: x for x in inspect(c).get_columns("collection_runs")})
    assert cols["status"]["nullable"] and cols["finished_at"]["nullable"]
    assert "'{}'" in str(cols["changed_days"]["default"])


async def test_downgrade_one_revision_keeps_dam_tables(sessions, alembic_config, repository):
    await repository.save_records([], {})
    await asyncio.to_thread(command.downgrade, alembic_config, "-1")
    try:
        async with sessions() as s:
            tables = await (await s.connection()).run_sync(lambda c: set(inspect(c).get_table_names()))
        assert "collection_runs" not in tables
        assert {"dam_prices", "dam_days", "dam_raw_snapshots"} <= tables
    finally:
        await asyncio.to_thread(command.upgrade, alembic_config, "head")


# 2. Advisory lock

async def test_second_holder_is_refused_without_waiting(engine):
    async with dam_writer_lock(engine) as first:
        assert first
        async with asyncio.timeout(2):  # неблокувальна спроба не має чекати
            async with dam_writer_lock(engine) as second:
                assert not second


async def test_lock_released_after_exception(engine):
    with pytest.raises(RuntimeError):
        async with dam_writer_lock(engine) as acquired:
            assert acquired
            raise RuntimeError("збій усередині")
    async with dam_writer_lock(engine) as again:
        assert again


async def test_lock_released_when_holder_connection_dies(engine, database_url):
    dying = create_async_engine(database_url, poolclass=NullPool)
    conn = await dying.connect()
    assert (await conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": DAM_WRITER_LOCK_KEY})).scalar_one()
    await conn.commit()
    async with dam_writer_lock(engine) as while_held:
        assert not while_held
    await conn.close()  # «процес загинув»
    await dying.dispose()
    async with dam_writer_lock(engine) as after:
        assert after


async def test_sequential_acquisitions(engine):
    for _ in range(3):
        async with dam_writer_lock(engine) as acquired:
            assert acquired


# 3. Детекція змін

def test_identical_hashes_give_empty_diff():
    h = {date(2026, 7, 1): "a", date(2026, 7, 2): "b"}
    assert changed_days(h, dict(h)) == []


async def test_new_day_detected(repository, runs, engine):
    await collect(FakeDamSource({Q3: q3_file(2)}), repository, runs, engine)
    outcome = await collect(FakeDamSource({Q3: q3_file(3)}), repository, runs, engine)
    assert outcome.changed_days == (date(2026, 7, 3),)


async def test_retroactive_recalculation_detected(repository, runs, engine):
    await collect(FakeDamSource({Q3: q3_file(3)}), repository, runs, engine)
    edited = q3_file(3, changed={date(2026, 7, 2): "555.55"})
    outcome = await collect(FakeDamSource({Q3: edited}), repository, runs, engine)
    assert outcome.changed_days == (date(2026, 7, 2),)


class SpyRepository(DamRepository):
    saved: list

    async def save_collected(self, records, day_hashes, fetches):
        self.saved = list(records)
        await super().save_collected(self.saved, day_hashes, fetches)


async def test_only_changed_days_are_written(sessions, runs, engine):
    repository = SpyRepository(sessions)
    await collect(FakeDamSource({Q3: q3_file(90)}), repository, runs, engine)
    edited = q3_file(90, changed={date(2026, 8, 15): "1.00"})
    await collect(FakeDamSource({Q3: edited}), repository, runs, engine)
    assert {r.delivery_date for r in repository.saved} == {date(2026, 8, 15)}
    assert len(repository.saved) == 24


# 4. Сценарій збору

async def test_first_collection_is_success(repository, runs, engine, sessions):
    outcome = await collect(FakeDamSource({Q3: q3_file(2)}), repository, runs, engine)
    assert outcome.status == "success"
    assert outcome.changed_days == (date(2026, 7, 1), date(2026, 7, 2))
    assert await rows(sessions) == 48


async def test_repeat_is_no_changes(repository, runs, engine, sessions):
    source = FakeDamSource({Q3: q3_file(2)})
    await collect(source, repository, runs, engine)
    outcome = await collect(source, repository, runs, engine)
    assert (outcome.status, outcome.changed_days) == ("no_changes", ())
    assert await rows(sessions) == 48


async def test_empty_source_is_no_data_not_error(repository, runs, engine):
    outcome = await collect(FakeDamSource(), repository, runs, engine)
    assert outcome.status == "no_data" and outcome.error is None
    info = await runs.get(outcome.run_id)
    assert info.status == "no_data" and info.error_message is None


class DownSource(FakeDamSource):
    async def fetch_raw(self, quarter):
        raise FetchError("ОРЕЕ недоступний після 3 спроб")


async def test_source_failure_is_error_and_data_untouched(repository, runs, engine, sessions):
    await collect(FakeDamSource({Q3: q3_file(2)}), repository, runs, engine)
    before = await repository.get_records(date(2026, 7, 1), date(2026, 7, 31))
    outcome = await collect(DownSource(), repository, runs, engine)
    assert outcome.status == "error" and "ОРЕЕ недоступний" in outcome.error
    assert (await runs.get(outcome.run_id)).error_message == outcome.error
    assert await repository.get_records(date(2026, 7, 1), date(2026, 7, 31)) == before


class RecordsFailRepository(DamRepository):
    async def _upsert_records(self, session, records, day_hashes):
        raise RuntimeError("сховище зірвалось")


async def test_storage_failure_is_error_without_partial_changes(sessions, runs, engine):
    outcome = await collect(FakeDamSource({Q3: q3_file(2)}), RecordsFailRepository(sessions), runs, engine)
    assert outcome.status == "error"
    assert await rows(sessions) == 0


async def test_snapshot_not_saved_when_records_step_fails(sessions, runs, engine):
    await collect(FakeDamSource({Q3: q3_file(2)}), RecordsFailRepository(sessions), runs, engine)
    assert await rows(sessions, DamRawSnapshot) == 0


class SnapshotFailRepository(DamRepository):
    async def _insert_snapshot(self, session, *args):
        raise RuntimeError("знімок зірвався")


async def test_snapshot_failure_rolls_back_records_and_hashes(sessions, runs, engine):
    repository = SnapshotFailRepository(sessions)
    outcome = await collect(FakeDamSource({Q3: q3_file(2)}), repository, runs, engine)
    assert outcome.status == "error"
    assert await rows(sessions) == 0
    assert await repository.get_day_hashes(date(2026, 7, 1), date(2026, 7, 31)) == {}


# 5. Журнал

class DiesMidway(FakeDamSource):
    async def fetch_raw(self, quarter):
        raise asyncio.CancelledError  # процес зупинено: не Exception, обробник його не ловить


async def test_run_row_exists_before_source_is_contacted(repository, runs, engine, sessions):
    with pytest.raises(asyncio.CancelledError):
        await collect(DiesMidway(), repository, runs, engine)
    async with sessions() as s:
        run = (await s.execute(select(CollectionRun))).scalar_one()
    assert run.finished_at is None and run.status is None


async def test_run_row_completed(repository, runs, engine):
    outcome = await collect(FakeDamSource({Q3: q3_file(2)}), repository, runs, engine)
    info = await runs.get(outcome.run_id)
    assert info.status == "success"
    assert info.finished_at >= info.started_at
    assert info.changed_days == (date(2026, 7, 1), date(2026, 7, 2))


async def test_error_row_survives_rollback(sessions, runs, engine):
    outcome = await collect(FakeDamSource({Q3: q3_file(2)}), RecordsFailRepository(sessions), runs, engine)
    info = await runs.get(outcome.run_id)
    assert info.status == "error" and "сховище зірвалось" in info.error_message


async def test_trigger_recorded(repository, runs, engine):
    a = await collect(FakeDamSource(), repository, runs, engine, trigger="scheduled")
    b = await collect(FakeDamSource(), repository, runs, engine, trigger="manual")
    assert (await runs.get(a.run_id)).trigger == "scheduled"
    assert (await runs.get(b.run_id)).trigger == "manual"


# 6. Взаємне виключення на рівні сценарію

async def test_collect_skipped_when_lock_held(repository, runs, engine, sessions, held_lock):
    source = FakeDamSource({Q3: q3_file(2)})
    async with asyncio.timeout(2):  # не чекає на звільнення
        outcome = await collect(source, repository, runs, engine)
    assert outcome.status == "skipped_locked" and outcome.error is None
    assert source.calls == []
    assert await rows(sessions) == 0
    info = await runs.get(outcome.run_id)
    assert info.status == "skipped_locked" and info.error_message is None


# 7. Бекфіл під спільним блокуванням

async def test_backfill_refused_while_lock_held(repository, engine, sessions, held_lock):
    out = io.StringIO()
    source = FakeDamSource({Q3: q3_file(2)})
    code = await run_locked_backfill(engine, source, repository, [Q3], delay=0, out=out)
    assert code == 1
    assert "блокування" in out.getvalue()
    assert source.calls == [] and await rows(sessions) == 0


async def test_collect_during_backfill_is_skipped(repository, runs, engine):
    started, release = asyncio.Event(), asyncio.Event()

    class SlowSource(FakeDamSource):
        async def fetch_raw(self, quarter):
            started.set()
            await release.wait()
            return await super().fetch_raw(quarter)

    backfill = asyncio.create_task(run_locked_backfill(
        engine, SlowSource({Q3: q3_file(2)}), repository, [Q3], delay=0, out=io.StringIO()
    ))
    await started.wait()
    outcome = await collect(FakeDamSource({Q3: q3_file(2)}), repository, runs, engine)
    release.set()
    assert await backfill == 0
    assert outcome.status == "skipped_locked"


# 8. Читання стану

async def test_last_update_is_last_success_not_last_run(repository, runs, engine):
    source = FakeDamSource({Q3: q3_file(2)})
    first = await collect(source, repository, runs, engine)
    await collect(source, repository, runs, engine)  # no_changes
    state = await runs.state()
    assert state.last_run.status == "no_changes"
    assert state.last_update.id == first.run_id


async def test_recent_errors_filtered_newest_first(repository, runs, engine):
    e1 = await collect(DownSource(), repository, runs, engine)
    await collect(FakeDamSource(), repository, runs, engine)  # no_data
    e2 = await collect(DownSource(), repository, runs, engine)
    state = await runs.state()
    assert [r.id for r in state.recent_errors] == [e2.run_id, e1.run_id]
    assert all(r.status == "error" for r in state.recent_errors)


async def test_empty_log_state(runs):
    state = await runs.state()
    assert state.last_run is None and state.last_update is None and state.recent_errors == ()


async def test_unfinished_run_does_not_break_state(repository, runs, engine):
    with pytest.raises(asyncio.CancelledError):
        await collect(DiesMidway(), repository, runs, engine)
    state = await runs.state()
    assert state.last_run.finished_at is None and state.last_run.status is None
    assert state.last_update is None
