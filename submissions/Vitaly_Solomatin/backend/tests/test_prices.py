from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.dam_source.hashing import day_hashes
from app.dam_source.models import DamRecord
from app.dam_source.parser import parse_csv
from tests.fakes import FakeDamSource
from tests.test_api import running

D = Decimal
JULY_1 = date(2026, 7, 1)


def rec(day, period, price, sell="1.0", buy="1.0", dsell="5.0", dbuy="2.0"):
    return DamRecord(day, period, D(price), D(sell), D(buy), D(dsell), D(dbuy))


async def save(repository, records):
    await repository.save_records(records, day_hashes(records))


def known_day(day=JULY_1):
    # min 100, max 600, проста середня 300.00, зважена (100+200+600*2)/4 = 375.00
    return [rec(day, 1, "100.00"), rec(day, 2, "200.00"), rec(day, 3, "600.00", sell="2.0", buy="2.0")]


def full_day(day, price="100.00", periods=24):
    return [rec(day, p, price) for p in range(1, periods + 1)]


async def prices(engine, **params):
    async with running(engine, FakeDamSource()) as (_, client):
        return await client.get("/prices", params=params)


# 1. Репозиторій

async def test_daily_one_row_per_day_ordered(repository):
    await save(repository, full_day(date(2026, 7, 2)) + full_day(JULY_1))
    days = await repository.get_daily(JULY_1, date(2026, 7, 2))
    assert [d.delivery_date for d in days] == [JULY_1, date(2026, 7, 2)]


async def test_daily_aggregates_exact(repository):
    await save(repository, known_day())
    [d] = await repository.get_daily(JULY_1, JULY_1)
    assert (d.price_min, d.price_max) == (D("100.00"), D("600.00"))
    assert d.price_avg == D("300.00") and d.price_weighted == D("375.00")
    assert (d.volume_sell, d.volume_buy) == (D("4.0"), D("4.0"))
    assert (d.declared_volume_sell, d.declared_volume_buy) == (D("15.0"), D("6.0"))
    assert d.periods == 3
    assert all(isinstance(v, Decimal) for v in (d.price_avg, d.price_weighted, d.volume_sell))


async def test_zero_volume_gives_no_weighted_price(repository):
    await save(repository, [rec(JULY_1, p, "100.00", sell="0.0") for p in (1, 2)])
    [d] = await repository.get_daily(JULY_1, JULY_1)
    assert d.price_weighted is None
    assert d.price_avg == D("100.00") and d.periods == 2


async def test_daily_periods_on_dst_days(repository, fixture_bytes):
    for name in ("dam_2025_Q1.csv", "dam_2025_Q4.csv"):
        await save(repository, parse_csv(fixture_bytes(name)))
    days = {d.delivery_date: d.periods for d in await repository.get_daily(date(2025, 1, 1), date(2025, 12, 31))}
    assert days[date(2025, 3, 30)] == 23 and days[date(2025, 10, 26)] == 25


async def test_daily_empty_range(repository):
    assert await repository.get_daily(JULY_1, JULY_1) == []


async def test_daily_matches_oree_published_value(repository, fixture_bytes):
    await save(repository, parse_csv(fixture_bytes("dam_2026_Q3.csv")))
    [d] = await repository.get_daily(date(2026, 9, 26), date(2026, 9, 26))
    assert d.price_weighted == D("6560.60") and d.volume_sell == D("72279.5")


# 2. Маршрут

async def test_hourly_columnar(repository, engine):
    await save(repository, full_day(JULY_1))
    body = (await prices(engine, date_from="2026-07-01", date_to="2026-07-01", resolution="hour")).json()
    assert body["resolution"] == "hour"
    assert body["period"] == list(range(1, 25))
    for field in ("delivery_date", "price", "volume_sell", "volume_buy", "declared_volume_sell", "declared_volume_buy"):
        assert len(body[field]) == 24, field
    assert body["price"][0] == 100.0 and body["delivery_date"][0] == "2026-07-01"


async def test_default_resolution_is_hour(repository, engine):
    await save(repository, full_day(JULY_1))
    body = (await prices(engine, date_from="2026-07-01", date_to="2026-07-01")).json()
    assert body["resolution"] == "hour"


async def test_hourly_dst_day_has_25_periods(repository, engine, fixture_bytes):
    await save(repository, parse_csv(fixture_bytes("dam_2025_Q4.csv")))
    body = (await prices(engine, date_from="2025-10-26", date_to="2025-10-26")).json()
    assert body["period"] == list(range(1, 26))


async def test_daily_contract(repository, engine):
    await save(repository, known_day() + [rec(date(2026, 7, 2), 1, "50.00", sell="0.0")])
    r = await prices(engine, date_from="2026-07-01", date_to="2026-07-02", resolution="day")
    body = r.json()
    fields = {"delivery_date", "price_min", "price_max", "price_avg", "price_weighted",
              "volume_sell", "volume_buy", "declared_volume_sell", "declared_volume_buy", "periods"}
    assert set(body) == fields | {"resolution", "date_from", "date_to"}
    assert body["resolution"] == "day"
    assert {len(body[f]) for f in fields} == {2}
    assert body["price_weighted"] == [375.0, None]
    assert body["periods"] == [3, 1]


async def test_inclusive_bounds_and_empty_range(repository, engine):
    await save(repository, [r for i in range(10) for r in full_day(JULY_1 + timedelta(days=i))])
    body = (await prices(engine, date_from="2026-07-03", date_to="2026-07-05", resolution="day")).json()
    assert body["delivery_date"] == ["2026-07-03", "2026-07-04", "2026-07-05"]
    empty = await prices(engine, date_from="2027-01-01", date_to="2027-01-02")
    assert empty.status_code == 200 and empty.json()["price"] == [] and empty.json()["period"] == []


async def test_no_credentials_needed(repository, engine):
    await save(repository, full_day(JULY_1))
    async with running(engine, FakeDamSource()) as (_, client):
        r = await client.get("/prices", params={"date_from": "2026-07-01", "date_to": "2026-07-01"})
    assert r.status_code == 200 and len(r.json()["price"]) == 24


# 3. Валідація

@pytest.mark.parametrize("params", [
    {"date_from": "2026-07-01"},
    {"date_from": "2026-13-01", "date_to": "2026-12-31"},
    {"date_from": "2026-07-01", "date_to": "2026-07-02", "resolution": "week"},
], ids=["missing-date_to", "bad-date", "bad-resolution"])
async def test_invalid_params_are_422(engine, params):
    assert (await prices(engine, **params)).status_code == 422


class ExplodingRepo:
    async def get_records(self, *a):
        raise AssertionError("звернення до БД")

    get_daily = get_records


@pytest.mark.parametrize("resolution", ["hour", "day"])
async def test_inverted_range_rejected_before_db(engine, resolution):
    async with running(engine, FakeDamSource()) as (app, client):
        app.state.repository = ExplodingRepo()
        r = await client.get("/prices",
                             params={"date_from": "2026-07-05", "date_to": "2026-07-01", "resolution": resolution})
    assert r.status_code == 422


async def test_hourly_range_limit(engine):
    ok = await prices(engine, date_from="2024-01-01", date_to="2024-12-31", resolution="hour")  # 366 діб
    too_long = await prices(engine, date_from="2024-01-01", date_to="2025-01-01", resolution="hour")  # 367
    assert ok.status_code == 200
    assert too_long.status_code == 422 and "resolution=day" in too_long.json()["detail"]


async def test_daily_has_no_range_limit(engine):
    r = await prices(engine, date_from="2019-01-01", date_to="2026-12-31", resolution="day")
    assert r.status_code == 200
