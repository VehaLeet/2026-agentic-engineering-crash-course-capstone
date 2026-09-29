from datetime import datetime, timedelta, timezone

import pytest

from app.settings import ScheduleSettingsStore
from tests.test_api import GateSource, running
from tests.test_collection import Q3, q3_file
from tests.test_schedule_runs import finished, runs, scheduled_app, wait_for

UTC = timezone.utc
SLACK = timedelta(seconds=5)


def parse(value: str | None) -> datetime | None:
    return value and datetime.fromisoformat(value)


async def settled(sessions, client) -> dict:
    """Дочекатися стартового планового запуску: після нього next_run_at — через інтервал."""
    await wait_for(lambda: finished(sessions))
    return (await client.get("/settings/schedule")).json()


# 1. Читання

async def test_get_enabled_schedule(engine, sessions):
    async with scheduled_app(engine, GateSource({Q3: q3_file(2)})) as (_, client):
        r = await client.get("/settings/schedule")
        body = await settled(sessions, client)
    assert r.status_code == 200
    assert (body["enabled"], body["interval_minutes"]) == (True, 60)
    assert parse(body["next_run_at"]) > datetime.now(UTC)
    assert parse(body["next_run_at"]).tzinfo is not None


async def test_get_disabled_schedule(engine):
    async with scheduled_app(engine, GateSource(), enabled=False) as (_, client):
        body = (await client.get("/settings/schedule")).json()
    assert body == {"enabled": False, "interval_minutes": 60, "next_run_at": None}


async def test_get_without_scheduler_has_no_next_run(engine):
    async with running(engine, GateSource()) as (_, client):
        r = await client.get("/settings/schedule")
    assert r.status_code == 200
    assert r.json() == {"enabled": True, "interval_minutes": 60, "next_run_at": None}


# 2. Зміна

async def test_put_new_interval_applies_now_and_survives_restart(engine, sessions):
    async with scheduled_app(engine, GateSource({Q3: q3_file(2)})) as (_, client):
        await settled(sessions, client)
        r = await client.put("/settings/schedule", json={"enabled": True, "interval_minutes": 15})
    assert r.status_code == 200
    body = r.json()
    assert (body["enabled"], body["interval_minutes"]) == (True, 15)
    assert abs(parse(body["next_run_at"]) - (datetime.now(UTC) + timedelta(minutes=15))) < SLACK
    async with running(engine, GateSource()) as (_, client):  # новий екземпляр — імітація рестарту
        assert (await client.get("/settings/schedule")).json()["interval_minutes"] == 15


async def test_put_disable_keeps_running_tick_alive(engine, sessions):
    source = GateSource({Q3: q3_file(2)}, gated=True)
    async with scheduled_app(engine, source) as (app, client):
        await source.entered.wait()
        r = await client.put("/settings/schedule", json={"enabled": False, "interval_minutes": 60})
        assert r.json() == {"enabled": False, "interval_minutes": 60, "next_run_at": None}
        source.gate.set()
        [run] = await wait_for(lambda: finished(sessions))
        assert run.status == "success"
        assert app.state.scheduler.next_run_at() is None
    assert len(await runs(sessions)) == 1


async def test_put_reenable(engine):
    async with scheduled_app(engine, GateSource(), enabled=False) as (_, client):
        body = (await client.put("/settings/schedule", json={"enabled": True, "interval_minutes": 60})).json()
    assert abs(parse(body["next_run_at"]) - (datetime.now(UTC) + timedelta(minutes=60))) < SLACK


# 3. Відхилення

@pytest.mark.parametrize("body", [
    {"enabled": True, "interval_minutes": 4},
    {"enabled": True, "interval_minutes": 1441},
    {"enabled": True, "interval_minutes": 0},
    {"enabled": True, "interval_minutes": -5},
    {"enabled": True, "interval_minutes": "15"},
    {"enabled": True, "interval_minutes": "abc"},
    {"enabled": True, "interval_minutes": 7.5},
    {"enabled": True, "interval_minutes": True},
    {"interval_minutes": 15},
    {"enabled": True},
])
async def test_put_invalid_body_changes_nothing(engine, sessions, body):
    async with scheduled_app(engine, GateSource({Q3: q3_file(2)})) as (_, client):
        before = await settled(sessions, client)
        r = await client.put("/settings/schedule", json=body)
        after = (await client.get("/settings/schedule")).json()
    assert r.status_code == 422
    assert after == before
    stored = await ScheduleSettingsStore(sessions).get()
    assert (stored.enabled, stored.interval_minutes) == (True, 60)
