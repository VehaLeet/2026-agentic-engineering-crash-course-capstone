import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

import httpx
import pytest
from fastapi.routing import APIRoute
from sqlalchemy import func, select

from app.api.app import create_app
from app.api.runs_manager import RunManager
from app.api.settings import ApiSettings, ConfigError
from app.backfill import parse_args
from app.collection.collect import collect_once
from app.collection.runs import RunLog
from app.dam_source.models import FetchError, Quarter
from app.storage.models import CollectionRun
from app.timeutil import kyiv_today
from tests.conftest import ROOT
from tests.fakes import FakeDamSource
from tests.test_collection import Q3, REF, held_lock, q3_file  # noqa: F401 (held_lock — фікстура)

SETTINGS = ApiSettings("admin", "s3cret")
AUTH = ("admin", "s3cret")
UTC = timezone.utc


class GateSource(FakeDamSource):
    """Підставне джерело: записує опорні дати і (за потреби) тримає збір до відкриття «воріт»."""

    def __init__(self, files=None, gated=False, fail=False):
        super().__init__(files)
        self.gate = asyncio.Event()
        self.entered = asyncio.Event()
        self.reference_dates: list[date] = []
        if not gated:
            self.gate.set()
        self.fail = fail

    async def collect_for(self, reference_date):
        self.reference_dates.append(reference_date)
        return await super().collect_for(reference_date)

    async def fetch_raw(self, quarter):
        self.entered.set()
        await self.gate.wait()
        if self.fail:
            raise FetchError("ОРЕЕ недоступний після 3 спроб")
        return await super().fetch_raw(quarter)


@asynccontextmanager
async def running(engine, source, now=lambda: datetime(2026, 9, 28, 9, 0, tzinfo=UTC)):
    app = create_app(SETTINGS, engine=engine, source=source, now=now)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield app, client


async def run_rows(sessions) -> int:
    async with sessions() as s:
        return (await s.execute(select(func.count()).select_from(CollectionRun))).scalar_one()


# 1. Конфігурація

def test_env_example_has_api_credentials():
    text = (ROOT / ".env.example").read_text()
    assert "API_USERNAME=" in text and "API_PASSWORD=" in text


@pytest.mark.parametrize("missing", ["API_USERNAME", "API_PASSWORD"])
def test_app_refuses_to_build_without_credentials(monkeypatch, missing):
    monkeypatch.setenv("API_USERNAME", "admin")
    monkeypatch.setenv("API_PASSWORD", "s3cret")
    monkeypatch.delenv(missing)
    with pytest.raises(ConfigError, match=missing):
        create_app()


def test_settings_repr_hides_password():
    assert "s3cret" not in repr(SETTINGS)


# 2. Опорна дата

@pytest.mark.parametrize("now, expected", [
    (datetime(2026, 9, 30, 22, 30, tzinfo=UTC), date(2026, 10, 1)),
    (datetime(2026, 12, 31, 22, 30, tzinfo=UTC), date(2027, 1, 1)),
    (datetime(2026, 9, 30, 20, 0, tzinfo=UTC), date(2026, 9, 30)),
])
def test_kyiv_today(now, expected):
    assert kyiv_today(now) == expected


def test_backfill_default_upper_bound_uses_kyiv_date():
    quarters, _ = parse_args([], today=kyiv_today(datetime(2026, 12, 31, 22, 30, tzinfo=UTC)))
    assert quarters[-1] == Quarter(2027, 1)


# 3. Збір із наперед створеним запуском

async def test_collect_uses_precreated_run(repository, sessions, engine):
    runs = RunLog(sessions)
    run_id = await runs.start("manual")
    outcome = await collect_once(FakeDamSource({Q3: q3_file(2)}), repository, runs, engine, REF, "manual", run_id)
    assert outcome.run_id == run_id and outcome.status == "success"
    assert await run_rows(sessions) == 1


async def test_precreated_run_finished_as_skipped_when_locked(repository, sessions, engine, held_lock):
    runs = RunLog(sessions)
    run_id = await runs.start("manual")
    outcome = await collect_once(FakeDamSource(), repository, runs, engine, REF, "manual", run_id)
    assert outcome.status == "skipped_locked"
    assert (await runs.get(run_id)).status == "skipped_locked"
    assert await run_rows(sessions) == 1


# 4. Застосунок і автентифікація

async def test_lifespan_sets_up_run_manager(engine):
    async with running(engine, FakeDamSource()) as (app, _):
        assert isinstance(app.state.manager, RunManager)


async def test_no_credentials_is_401_with_basic_challenge(engine):
    async with running(engine, FakeDamSource()) as (_, client):
        r = await client.get("/status")
    assert r.status_code == 401
    assert r.headers["www-authenticate"].startswith("Basic")


@pytest.mark.parametrize("auth", [("admin", "wrong"), ("root", "s3cret")], ids=["password", "username"])
async def test_wrong_credentials_are_401(engine, auth):
    async with running(engine, FakeDamSource()) as (_, client):
        assert (await client.get("/status", auth=auth)).status_code == 401


async def test_wrong_password_on_collect_creates_no_run(engine, sessions):
    async with running(engine, FakeDamSource()) as (_, client):
        r = await client.post("/collect", auth=("admin", "wrong"))
    assert r.status_code == 401
    assert await run_rows(sessions) == 0


async def test_correct_credentials(engine):
    async with running(engine, FakeDamSource()) as (_, client):
        assert (await client.get("/status", auth=AUTH)).status_code == 200


async def test_health_needs_no_auth_and_reveals_nothing(engine):
    async with running(engine, FakeDamSource()) as (_, client):
        r = await client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


async def test_every_route_except_health_requires_auth(engine):
    async with running(engine, FakeDamSource()) as (app, client):
        public = {r.path for r in app.routes if isinstance(r, APIRoute)}
        protected = [r for r in app.state.protected_router.routes if isinstance(r, APIRoute)]
        assert public == {"/health"}
        assert {r.path for r in protected} == {"/collect", "/runs/{run_id}", "/status"}
        for route in protected:
            path = route.path.replace("{run_id}", "1")
            for method in route.methods:
                assert (await client.request(method, path)).status_code == 401, (method, path)
        for docs in ["/docs", "/redoc", "/openapi.json"]:
            assert (await client.get(docs)).status_code == 404


# 5. Фонові запуски

async def test_run_manager_tracks_and_drains_tasks():
    done = []

    async def job(run_id):
        await asyncio.sleep(0)
        done.append(run_id)

    manager = RunManager(job)
    manager.start(1)
    assert manager.active == 1
    await manager.wait_all()
    assert manager.active == 0 and done == [1]


async def test_collect_returns_202_with_run_reference(engine):
    async with running(engine, GateSource({Q3: q3_file(2)})) as (app, client):
        r = await client.post("/collect", auth=AUTH)
        await app.state.manager.wait_all()
    assert r.status_code == 202
    body = r.json()
    assert body == {"run_id": body["run_id"], "status_url": f"/runs/{body['run_id']}"}
    assert r.headers["location"] == f"/runs/{body['run_id']}"


async def test_collect_does_not_wait_for_source(engine):
    source = GateSource({Q3: q3_file(2)}, gated=True)
    async with running(engine, source) as (app, client):
        async with asyncio.timeout(1):
            r = await client.post("/collect", auth=AUTH)
        await source.entered.wait()
        pending = (await client.get(r.headers["location"], auth=AUTH)).json()
        assert pending["status"] is None and pending["finished_at"] is None
        source.gate.set()
        await app.state.manager.wait_all()


async def test_background_success_visible_via_run(engine):
    async with running(engine, GateSource({Q3: q3_file(2)})) as (app, client):
        run_id = (await client.post("/collect", auth=AUTH)).json()["run_id"]
        await app.state.manager.wait_all()
        run = (await client.get(f"/runs/{run_id}", auth=AUTH)).json()
    assert run["status"] == "success"
    assert run["changed_days"] == ["2026-07-01", "2026-07-02"]
    assert run["trigger"] == "manual"


async def test_background_failure_is_error_and_app_keeps_serving(engine):
    async with running(engine, GateSource(fail=True)) as (app, client):
        run_id = (await client.post("/collect", auth=AUTH)).json()["run_id"]
        await app.state.manager.wait_all()
        run = (await client.get(f"/runs/{run_id}", auth=AUTH)).json()
        health = await client.get("/health")
    assert run["status"] == "error" and "ОРЕЕ недоступний" in run["error_message"]
    assert health.status_code == 200


async def test_two_concurrent_collects(engine):
    source = GateSource({Q3: q3_file(2)}, gated=True)
    async with running(engine, source) as (app, client):
        first = (await client.post("/collect", auth=AUTH)).json()["run_id"]
        await source.entered.wait()  # перший тримає блокування
        second = (await client.post("/collect", auth=AUTH)).json()["run_id"]
        assert first != second
        while (await client.get(f"/runs/{second}", auth=AUTH)).json()["status"] is None:
            await asyncio.sleep(0.01)  # другий завершується одразу, не чекаючи першого
        source.gate.set()
        await app.state.manager.wait_all()
        statuses = [(await client.get(f"/runs/{i}", auth=AUTH)).json()["status"] for i in (first, second)]
    assert statuses == ["success", "skipped_locked"]


async def test_reference_date_is_kyiv_today(engine):
    source = GateSource()
    now = lambda: datetime(2026, 9, 30, 22, 30, tzinfo=UTC)
    async with running(engine, source, now=now) as (app, client):
        await client.post("/collect", auth=AUTH)
        await app.state.manager.wait_all()
    assert source.reference_dates == [date(2026, 10, 1)]


async def test_shutdown_cancels_unfinished_run(engine, sessions):
    source = GateSource({Q3: q3_file(2)}, gated=True)
    async with running(engine, source) as (app, client):
        run_id = (await client.post("/collect", auth=AUTH)).json()["run_id"]
        await source.entered.wait()
        [task] = app.state.manager._tasks
    assert task.cancelled()
    info = await RunLog(sessions).get(run_id)
    assert info.finished_at is None and info.status is None


# 6. Читання стану

async def test_run_contract(engine):
    async with running(engine, GateSource({Q3: q3_file(2)})) as (app, client):
        run_id = (await client.post("/collect", auth=AUTH)).json()["run_id"]
        await app.state.manager.wait_all()
        run = (await client.get(f"/runs/{run_id}", auth=AUTH)).json()
    assert set(run) == {"id", "started_at", "finished_at", "status", "trigger", "changed_days", "error_message"}
    for field in ("started_at", "finished_at"):
        assert datetime.fromisoformat(run[field]).utcoffset() is not None
    assert all(date.fromisoformat(d) for d in run["changed_days"])


async def test_unknown_and_invalid_run_ids(engine):
    async with running(engine, FakeDamSource()) as (_, client):
        missing = await client.get("/runs/999999", auth=AUTH)
        invalid = await client.get("/runs/abc", auth=AUTH)
    assert missing.status_code == 404 and missing.json() == {"detail": "run not found"}
    assert invalid.status_code == 422


async def test_status_last_run_vs_last_update(engine):
    async with running(engine, GateSource({Q3: q3_file(2)})) as (app, client):
        first = (await client.post("/collect", auth=AUTH)).json()["run_id"]
        await app.state.manager.wait_all()
        await client.post("/collect", auth=AUTH)  # ті самі дані -> no_changes
        await app.state.manager.wait_all()
        state = (await client.get("/status", auth=AUTH)).json()
    assert state["last_run"]["status"] == "no_changes"
    assert state["last_update"]["id"] == first
    assert state["recent_errors"] == []


async def test_status_on_empty_log(engine):
    async with running(engine, FakeDamSource()) as (_, client):
        r = await client.get("/status", auth=AUTH)
    assert r.status_code == 200
    assert r.json() == {"last_run": None, "last_update": None, "recent_errors": []}
