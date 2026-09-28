"""Storage contract exercised against a migrated, disposable Postgres database."""

from datetime import date, timedelta
from decimal import Decimal
import json
import subprocess

import pytest
from alembic import command
from sqlalchemy import event, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.dam_source.hashing import content_hash, day_hashes
from app.dam_source.models import DamRecord
from app.dam_source.parser import parse_csv
from app.storage.database import database_url as configured_database_url, make_engine
from app.storage.models import DamDay, DamPrice, DamRawSnapshot
from tests.conftest import ROOT, postgres_env_file, postgres_image


DAY = date(2026, 7, 1)


def record(day=DAY, period=1, price="6000.00"):
    return DamRecord(day, period, Decimal(price), Decimal("12.3"), Decimal("14.5"),
                     Decimal("16.7"), Decimal("18.9"))


def day_records(day=DAY, count=24):
    return [record(day, period) for period in range(1, count + 1)]


async def count(sessions, model):
    async with sessions() as session:
        return len((await session.execute(select(model))).scalars().all())


def test_image_tag_shared_by_compose_and_fixture():
    compose = (ROOT / "docker-compose.yml").read_text()
    assert "image: ${POSTGRES_IMAGE}" in compose
    assert "POSTGRES_IMAGE=postgres:16" in (ROOT / ".env.example").read_text()
    config = subprocess.run(
        ["docker", "compose", "--env-file", str(postgres_env_file()), "config", "--format", "json"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    assert json.loads(config.stdout)["services"]["postgres"]["image"] == postgres_image()


async def test_connection_uses_environment_and_select_one(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    assert configured_database_url() == database_url
    engine = make_engine()
    try:
        async with engine.connect() as conn:
            assert (await conn.execute(text("SELECT 1"))).scalar_one() == 1
    finally:
        await engine.dispose()
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(RuntimeError):
        configured_database_url()


@pytest.fixture(scope="module")
def shared_container_url(database_url):
    return database_url


def test_session_container_is_shared_a(database_url, shared_container_url):
    assert database_url.startswith("postgresql+asyncpg://")
    assert database_url == shared_container_url


def test_session_container_is_shared_b(database_url, shared_container_url):
    assert database_url == shared_container_url


async def test_migration_version_and_schema(sessions):
    async with sessions() as session:
        assert (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one() == "0001_dam_storage"
        schema = await session.connection()
        tables = await schema.run_sync(lambda conn: set(inspect(conn).get_table_names()))
        pk = await schema.run_sync(lambda conn: inspect(conn).get_pk_constraint("dam_prices"))
        uniques = await schema.run_sync(lambda conn: inspect(conn).get_unique_constraints("dam_raw_snapshots"))
    assert {"dam_prices", "dam_days", "dam_raw_snapshots", "alembic_version"} <= tables
    assert pk["constrained_columns"] == ["delivery_date", "period"]
    assert any(u["column_names"] == ["content_hash"] for u in uniques)


def test_upgrade_twice_and_downgrade(database_url, alembic_config):
    command.upgrade(alembic_config, "head")
    command.upgrade(alembic_config, "head")
    command.check(alembic_config)
    try:
        command.downgrade(alembic_config, "base")
        command.upgrade(alembic_config, "head")
    finally:
        command.upgrade(alembic_config, "head")


@pytest.mark.parametrize("period", [0, 26])
async def test_period_check_is_in_postgres(sessions, period):
    async with sessions() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                await session.execute(text("""INSERT INTO dam_prices
                    (delivery_date, period, price, volume_sell, volume_buy, declared_volume_sell, declared_volume_buy)
                    VALUES (:day, :period, 1, 1, 1, 1, 1)"""), {"day": DAY, "period": period})


async def test_save_24_and_repeat(repository, sessions):
    rows = day_records()
    hashes = day_hashes(rows)
    await repository.save_records(rows, hashes)
    await repository.save_records(rows, hashes)
    assert await count(sessions, DamPrice) == 24
    assert await repository.get_records(DAY, DAY) == rows


async def test_same_key_in_independent_test(repository, sessions):
    await repository.save_records([record()], {DAY: "a" * 64})
    assert await count(sessions, DamPrice) == 1


async def test_changed_value_and_day_hash(repository, sessions):
    await repository.save_records([record(period=5)], {DAY: "a" * 64})
    await repository.save_records([record(period=5, price="6100.00")], {DAY: "b" * 64})
    assert await count(sessions, DamPrice) == 1
    [actual] = await repository.get_records(DAY, DAY)
    assert actual.period == 5 and actual.price == Decimal("6100.00")
    assert await repository.get_day_hashes(DAY, DAY) == {DAY: "b" * 64}


async def test_25_period_day(repository, sessions, fixture_bytes):
    day = date(2025, 10, 26)
    rows = [r for r in parse_csv(fixture_bytes("dam_2025_Q4.csv")) if r.delivery_date == day]
    assert len(rows) == 25
    await repository.save_records(rows, day_hashes(rows))
    await repository.save_records(rows, day_hashes(rows))
    assert await count(sessions, DamPrice) == 25


async def test_exact_decimals_and_negative_price(repository):
    rows = [record(price="-150.25")]
    await repository.save_records(rows, day_hashes(rows))
    [actual] = await repository.get_records(DAY, DAY)
    assert actual == rows[0]
    assert all(isinstance(getattr(actual, field), Decimal) for field in (
        "price", "volume_sell", "volume_buy", "declared_volume_sell", "declared_volume_buy"
    ))


async def test_bad_row_rolls_back_entire_batch(repository, sessions):
    rows = [record(), record(period=26)]
    with pytest.raises(IntegrityError):
        await repository.save_records(rows, {DAY: "a" * 64})
    assert await count(sessions, DamPrice) == 0
    assert await count(sessions, DamDay) == 0


async def test_failed_day_insert_rolls_back_prices(repository, sessions):
    engine = sessions.kw["bind"]

    def fail_day_insert(conn, cursor, statement, parameters, context, executemany):
        if "INSERT INTO dam_days" in statement:
            raise RuntimeError("simulated day write failure")

    event.listen(engine.sync_engine, "before_cursor_execute", fail_day_insert)
    try:
        with pytest.raises(RuntimeError, match="simulated"):
            await repository.save_records([record()], {DAY: "a" * 64})
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", fail_day_insert)
    assert await count(sessions, DamPrice) == 0
    assert await count(sessions, DamDay) == 0


async def test_day_hash_range(repository):
    days = [DAY + timedelta(days=i) for i in range(3)]
    rows = [record(day) for day in days]
    hashes = {day: str(i) * 64 for i, day in enumerate(days)}
    await repository.save_records(rows, hashes)
    assert await repository.get_day_hashes(days[0], days[-1]) == hashes


async def test_raw_snapshot_dedup_and_changed_content(repository, sessions, fixture_bytes):
    raw = fixture_bytes("dam_2026_Q3.csv")
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw
    first_hash = content_hash(raw)
    await repository.save_raw_snapshot(2026, 3, first_hash, raw)
    await repository.save_raw_snapshot(2026, 3, first_hash, raw)
    changed = raw + b"\r\n"
    await repository.save_raw_snapshot(2026, 3, content_hash(changed), changed)
    async with sessions() as session:
        snapshots = (await session.execute(select(DamRawSnapshot).order_by(DamRawSnapshot.id))).scalars().all()
    assert len(snapshots) == 2
    assert snapshots[0].content_hash == first_hash
    assert snapshots[0].raw_content == raw
    assert snapshots[1].raw_content == changed
    assert all(s.fetched_at is not None and s.year == 2026 and s.quarter == 3 for s in snapshots)


async def test_date_range_order_inclusive_and_empty(repository):
    days = [DAY + timedelta(days=i) for i in range(10)]
    rows = [record(day, period) for day in reversed(days) for period in (2, 1)]
    await repository.save_records(rows, {day: "a" * 64 for day in days})
    selected = await repository.get_records(days[2], days[4])
    assert [(r.delivery_date, r.period) for r in selected] == [
        (day, period) for day in days[2:5] for period in (1, 2)
    ]
    assert {r.delivery_date for r in await repository.get_records(days[0], days[1])} == set(days[:2])
    assert await repository.get_records(date(2026, 8, 1), date(2026, 8, 2)) == []


async def test_reversed_range_rejected_before_sql(repository, monkeypatch):
    def no_session():
        raise AssertionError("database was accessed")

    monkeypatch.setattr(repository, "sessions", no_session)
    with pytest.raises(ValueError):
        await repository.get_records(DAY + timedelta(days=1), DAY)


async def test_real_quarter_end_to_end(repository, sessions, fixture_bytes):
    raw = fixture_bytes("dam_2026_Q3.csv")
    rows = parse_csv(raw)
    hashes = day_hashes(rows)
    for _ in range(2):
        await repository.save_records(rows, hashes)
        await repository.save_raw_snapshot(2026, 3, content_hash(raw), raw)
    assert await count(sessions, DamPrice) == len(rows)
    assert await count(sessions, DamRawSnapshot) == 1
    assert await repository.get_records(min(hashes), max(hashes)) == sorted(rows, key=lambda r: (r.delivery_date, r.period))
    assert await repository.get_day_hashes(min(hashes), max(hashes)) == hashes
