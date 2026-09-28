import dataclasses
import random
from datetime import date
from decimal import Decimal

from app.dam_source.hashing import changed_days, content_hash, day_hashes
from app.dam_source.models import Quarter
from app.dam_source.parser import parse_csv
from tests.fakes import FakeDamSource

DAY = date(2025, 10, 26)


async def test_identical_downloads_give_same_content_hash(fixture_bytes):
    source = FakeDamSource({Quarter(2026, 3): fixture_bytes("dam_2026_Q3.csv")})
    a = await source.fetch_quarter(2026, 3)
    b = await source.fetch_quarter(2026, 3)
    assert a.content_hash == b.content_hash == content_hash(fixture_bytes("dam_2026_Q3.csv"))


def test_day_hash_ignores_row_order(fixture_bytes):
    records = parse_csv(fixture_bytes("dam_2025_Q4.csv"))
    shuffled = records[:]
    random.Random(42).shuffle(shuffled)
    assert day_hashes(records) == day_hashes(shuffled)


def test_day_hash_ignores_decimal_representation(fixture_bytes):
    records = [r for r in parse_csv(fixture_bytes("dam_2025_Q4.csv")) if r.delivery_date == DAY]
    padded = [dataclasses.replace(r, price=r.price.quantize(Decimal("0.0001"))) for r in records]
    assert day_hashes(records)[DAY] == day_hashes(padded)[DAY]


def test_day_hash_independent_of_other_days(fixture_bytes):
    records = parse_csv(fixture_bytes("dam_2025_Q4.csv"))
    only_day = [r for r in records if r.delivery_date == DAY]
    assert day_hashes(records)[DAY] == day_hashes(only_day)[DAY]


def test_new_day_is_the_only_change(fixture_bytes):
    records = parse_csv(fixture_bytes("dam_2025_Q4.csv"))
    last = max(r.delivery_date for r in records)
    before = day_hashes(r for r in records if r.delivery_date != last)
    assert changed_days(day_hashes(records), before) == [last]


def test_retroactive_recalculation_changes_only_that_day(fixture_bytes):
    records = parse_csv(fixture_bytes("dam_2025_Q4.csv"))
    before = day_hashes(records)
    edited = [
        dataclasses.replace(r, price=r.price + 1) if (r.delivery_date, r.period) == (DAY, 5) else r
        for r in records
    ]
    after = day_hashes(edited)
    assert changed_days(after, before) == [DAY]
    assert {d: h for d, h in after.items() if d != DAY} == {d: h for d, h in before.items() if d != DAY}
