import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pytest

from app.scheduling import JOB_ID, CollectScheduler, collect_tick
from app.settings import ScheduleSettings

UTC = timezone.utc
SLACK = timedelta(seconds=5)


def near(actual: datetime | None, expected: datetime) -> bool:
    return actual is not None and abs(actual - expected) < SLACK


@pytest.fixture
async def make_scheduler():
    created = []

    def make(tick=None):
        async def noop():
            pass

        s = CollectScheduler(tick or noop)
        created.append(s)
        return s

    yield make
    for s in created:
        s.shutdown()


# 1. Старт

async def test_start_enabled_runs_first_tick_now(make_scheduler):
    s = make_scheduler()
    s.start(ScheduleSettings(True, 60))
    assert near(s.next_run_at(), datetime.now(UTC))


async def test_start_disabled_has_no_next_run(make_scheduler):
    s = make_scheduler()
    s.start(ScheduleSettings(False, 60))
    assert s.next_run_at() is None


async def test_first_tick_fires_and_next_is_one_interval_later(make_scheduler):
    fired = asyncio.Event()

    async def tick():
        fired.set()

    s = make_scheduler(tick)
    started = datetime.now(UTC)
    s.start(ScheduleSettings(True, 60))
    async with asyncio.timeout(5):
        await fired.wait()
    assert near(s.next_run_at(), started + timedelta(minutes=60))


# 2. Перепланування

async def test_apply_new_interval_counts_from_now(make_scheduler):
    s = make_scheduler()
    s.start(ScheduleSettings(True, 60))
    s.apply(ScheduleSettings(True, 15))
    assert near(s.next_run_at(), datetime.now(UTC) + timedelta(minutes=15))


async def test_apply_disable_then_enable(make_scheduler):
    s = make_scheduler()
    s.start(ScheduleSettings(True, 60))
    s.apply(ScheduleSettings(False, 60))
    assert s.next_run_at() is None
    s.apply(ScheduleSettings(True, 60))
    assert near(s.next_run_at(), datetime.now(UTC) + timedelta(minutes=60))


async def test_enable_when_started_disabled(make_scheduler):
    s = make_scheduler()
    s.start(ScheduleSettings(False, 60))
    s.apply(ScheduleSettings(True, 30))
    assert near(s.next_run_at(), datetime.now(UTC) + timedelta(minutes=30))


async def test_reenable_counts_from_now_not_from_old_trigger(make_scheduler):
    s = make_scheduler()
    s.start(ScheduleSettings(True, 60))
    job = s._scheduler.get_job(JOB_ID)
    job.modify(next_run_time=datetime.now(UTC) + timedelta(minutes=3))  # старий тригер «майже тікнув»
    s.apply(ScheduleSettings(False, 60))
    s.apply(ScheduleSettings(True, 60))
    assert near(s.next_run_at(), datetime.now(UTC) + timedelta(minutes=60))


async def test_shutdown_removes_jobs(make_scheduler):
    s = make_scheduler()
    s.start(ScheduleSettings(True, 60))
    s.shutdown()
    assert s.next_run_at() is None
    s.shutdown()  # повторна зупинка безпечна


# 3. Тік

class BrokenRuns:
    async def start(self, trigger):
        raise ConnectionError("БД недоступна")


class NoManager:
    def start(self, run_id, trigger):
        raise AssertionError("не мало дійти до запуску збору")


async def test_tick_failure_is_logged_and_schedule_survives(make_scheduler, caplog):
    done = asyncio.Event()
    tick = collect_tick(BrokenRuns(), NoManager())

    async def observed():
        await tick()
        done.set()

    s = make_scheduler(observed)
    with caplog.at_level(logging.ERROR, logger="app.scheduling"):
        s.start(ScheduleSettings(True, 60))
        async with asyncio.timeout(5):
            await done.wait()
    assert "плановий збір не вдалося виконати" in caplog.text
    assert "БД недоступна" in caplog.text
    assert near(s.next_run_at(), datetime.now(UTC) + timedelta(minutes=60))


async def test_next_run_at_is_utc_regardless_of_host_zone(make_scheduler):
    # Без явного timezone тригер APScheduler 3.x бере зону хоста (tzlocal), а не планувальника.
    s = make_scheduler()
    s.start(ScheduleSettings(True, 60))
    assert s.next_run_at().utcoffset() == timedelta(0)
    s.apply(ScheduleSettings(True, 15))
    assert s.next_run_at().utcoffset() == timedelta(0)
